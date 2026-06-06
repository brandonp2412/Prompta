"""MCP Server — expose ChatGPT-Web2API as an MCP server.

Implements Tools, Resources, and Prompts following MCP best practices.

Transports:
    stdio  — for Claude Desktop, Cursor, etc. (default)
    sse    — for web clients (Craft Agent, custom hosts)

Run:
    chatgpt-web2api-mcp                         # stdio (default)
    chatgpt-web2api-mcp --transport sse          # SSE on port 8090
    chatgpt-web2api-mcp --transport sse --port 3000

Prerequisites:
    Run 'chatgpt-web2api' first to start Chrome with an authenticated session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any

from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .config import Config
from .cdp_driver import CDPDriver

logger = logging.getLogger(__name__)

# ── Global State ──────────────────────────────────────────────

_driver: CDPDriver | None = None
_config: Config | None = None


# ── Server Factory ────────────────────────────────────────────

def create_server() -> Server:
    """Create and configure the MCP server with all capabilities."""

    server = Server("chatgpt-web2api")

    # ── Tools (model-controlled) ──────────────────────────────

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name="chat_completion",
                description=(
                    "Send a message to ChatGPT and get a response. "
                    "Supports multi-turn conversation via conversation_id. "
                    "Supports project-scoped persistent memory via project_id."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The user message to send to ChatGPT",
                        },
                        "system_prompt": {
                            "type": "string",
                            "description": "System instructions prepended to the message. "
                                           "Changes to this value start a new conversation.",
                        },
                        "model": {
                            "type": "string",
                            "description": "Model slug: auto, gpt-5-5, gpt-5-mini, etc.",
                            "default": "auto",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "UUID of an existing conversation to continue. "
                                           "Omit to start a new chat or auto-continue.",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "ChatGPT project gizmo ID (e.g. g-p-abc123) "
                                           "for project-scoped persistent memory and instructions",
                        },
                    },
                    "required": ["message"],
                },
                annotations=mcp_types.ToolAnnotations(
                    title="ChatGPT Completion",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            ),
            mcp_types.Tool(
                name="list_models",
                description="List all ChatGPT models available on the account",
                inputSchema={"type": "object", "properties": {}},
                annotations=mcp_types.ToolAnnotations(
                    title="List Models",
                    readOnlyHint=True,
                    openWorldHint=True,
                ),
            ),
            mcp_types.Tool(
                name="list_projects",
                description="List ChatGPT projects (each has persistent memory and custom instructions)",
                inputSchema={"type": "object", "properties": {}},
                annotations=mcp_types.ToolAnnotations(
                    title="List Projects",
                    readOnlyHint=True,
                    openWorldHint=True,
                ),
            ),
            mcp_types.Tool(
                name="get_conversation",
                description="Retrieve the full message history of a conversation by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "UUID of the conversation to retrieve",
                        },
                    },
                    "required": ["conversation_id"],
                },
                annotations=mcp_types.ToolAnnotations(
                    title="Get Conversation",
                    readOnlyHint=True,
                    openWorldHint=True,
                ),
            ),
        ]

    @server.call_tool()
    async def call_tool(request: mcp_types.CallToolRequest) -> list[mcp_types.TextContent | mcp_types.EmbeddedResource]:
        name = request.params.name
        args = request.params.arguments or {}

        if _driver is None:
            return [mcp_types.TextContent(type="text", text="Error: not connected to Chrome. Run 'chatgpt-web2api' first.")]

        try:
            if name == "chat_completion":
                return await _handle_chat(args)
            elif name == "list_models":
                return await _handle_models()
            elif name == "list_projects":
                return await _handle_projects()
            elif name == "get_conversation":
                return await _handle_conversation(args)
            else:
                return [mcp_types.TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error("Tool '%s' failed: %s", name, e, exc_info=True)
            return [mcp_types.TextContent(type="text", text=f"Error: {e}")]

    # ── Resources (application-controlled) ────────────────────

    @server.list_resources()
    async def list_resources() -> list[mcp_types.Resource]:
        """List available ChatGPT projects as resources."""
        if _driver is None:
            return []
        try:
            projects = await _driver.get_projects()
            return [
                mcp_types.Resource(
                    uri=f"chatgpt://projects/{p['id']}",
                    name=p.get("name", "Unknown Project"),
                    description=f"ChatGPT project with {p.get('memory_scope', 'project_v2')} memory scope",
                    mimeType="application/json",
                )
                for p in projects if p.get("id")
            ]
        except Exception as e:
            logger.error("Failed to list resources: %s", e)
            return []

    @server.read_resource()
    async def read_resource(request: mcp_types.ReadResourceRequest) -> str | list[mcp_types.ResourceContents]:
        """Read a specific resource by URI."""
        uri = str(request.params.uri)

        if _driver is None:
            raise ValueError("Not connected to Chrome")

        if uri.startswith("chatgpt://projects/"):
            project_id = uri.split("/")[-1]
            projects = await _driver.get_projects()
            for p in projects:
                if p.get("id") == project_id:
                    return json.dumps(p, ensure_ascii=False, indent=2)
            raise ValueError(f"Project not found: {project_id}")

        elif uri == "chatgpt://models":
            models = await _driver.get_models()
            data = [{"id": m.get("slug", ""), "title": m.get("title", "")} for m in models]
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif uri == "chatgpt://account":
            return json.dumps({
                "user": _driver._user_name,
                "connected": _driver.is_connected,
            }, ensure_ascii=False, indent=2)

        raise ValueError(f"Unknown resource URI: {uri}")

    # ── Prompts (user-controlled) ─────────────────────────────

    @server.list_prompts()
    async def list_prompts() -> list[mcp_types.Prompt]:
        return [
            mcp_types.Prompt(
                name="ask-chatgpt",
                description="Send a question to ChatGPT with optional project context",
                arguments=[
                    mcp_types.PromptArgument(
                        name="question",
                        description="The question to ask",
                        required=True,
                    ),
                    mcp_types.PromptArgument(
                        name="project",
                        description="Project name or ID for scoped memory (optional)",
                        required=False,
                    ),
                ],
            ),
            mcp_types.Prompt(
                name="continue-chat",
                description="Continue the last conversation with a follow-up message",
                arguments=[
                    mcp_types.PromptArgument(
                        name="message",
                        description="Follow-up message",
                        required=True,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(request: mcp_types.GetPromptRequest) -> mcp_types.GetPromptResult:
        name = request.params.name
        args = request.params.arguments or {}

        if name == "ask-chatgpt":
            question = args.get("question", "")
            project = args.get("project", "")
            if not question:
                raise ValueError("question argument is required")

            tool_args = {"message": question}
            if project:
                # Try to resolve project name to ID
                projects = await _driver.get_projects() if _driver else []
                for p in projects:
                    if project.lower() in (p.get("name", "").lower(), p.get("id", "").lower()):
                        tool_args["project_id"] = p["id"]
                        break

            return mcp_types.GetPromptResult(
                description=f"Ask ChatGPT: {question[:60]}",
                messages=[
                    mcp_types.SamplingMessage(
                        role="user",
                        content=mcp_types.TextContent(
                            type="text",
                            text=(
                                f"Use the chat_completion tool to answer this question. "
                                f"Call it with these arguments:\n"
                                f"```json\n{json.dumps(tool_args, indent=2)}\n```\n\n"
                                f"Return the response content directly to the user."
                            ),
                        ),
                    ),
                ],
            )

        elif name == "continue-chat":
            message = args.get("message", "")
            if not message:
                raise ValueError("message argument is required")

            return mcp_types.GetPromptResult(
                description=f"Continue chat: {message[:60]}",
                messages=[
                    mcp_types.SamplingMessage(
                        role="user",
                        content=mcp_types.TextContent(
                            type="text",
                            text=(
                                f"Use the chat_completion tool with this message. "
                                f"Do NOT pass conversation_id — the tool will auto-continue "
                                f"the last conversation.\n\n"
                                f"Message: {message}"
                            ),
                        ),
                    ),
                ],
            )

        raise ValueError(f"Unknown prompt: {name}")

    return server


# ── Tool Handlers ─────────────────────────────────────────────

async def _handle_chat(args: dict) -> list[mcp_types.TextContent]:
    message = args.get("message", "")
    system_prompt = args.get("system_prompt", "")
    model = args.get("model", "auto")
    conversation_id = args.get("conversation_id")
    project_id = args.get("project_id") or (_config.chatgpt.default_project_id if _config else None)

    if not message:
        return [mcp_types.TextContent(type="text", text="Error: message is required")]

    # Build the full text
    if system_prompt:
        full_text = f"[System Instructions]\n{system_prompt}\n\n[User]\n{message}"
    else:
        full_text = message

    # Navigate
    if conversation_id:
        await _driver.navigate_conversation(conversation_id)
    elif _driver._current_conv_id and not system_prompt and not project_id:
        # Auto-continue existing conversation
        logger.info("Auto-continuing conversation: %s", _driver._current_conv_id)
    else:
        await _driver.navigate_new_chat(gizmo_id=project_id)

    # Send and collect
    full_response = ""
    conv_id = ""
    async for chunk in _driver.send_and_stream(full_text, timeout=120):
        if chunk.delta:
            full_response += chunk.delta
        if chunk.finish_reason:
            conv_id = _driver._current_conv_id or ""

    result = {
        "content": full_response,
        "model": model,
        "conversation_id": conv_id,
    }

    return [mcp_types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def _handle_models() -> list[mcp_types.TextContent]:
    models = await _driver.get_models()
    data = [{"id": m.get("slug", ""), "title": m.get("title", "")} for m in models]
    return [mcp_types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]


async def _handle_projects() -> list[mcp_types.TextContent]:
    projects = await _driver.get_projects()
    return [mcp_types.TextContent(type="text", text=json.dumps(projects, ensure_ascii=False))]


async def _handle_conversation(args: dict) -> list[mcp_types.TextContent]:
    conv_id = args.get("conversation_id", "")
    if not conv_id:
        return [mcp_types.TextContent(type="text", text="Error: conversation_id is required")]
    data = await _driver.get_conversation(conv_id)
    return [mcp_types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2)[:50000])]


# ── Transport ─────────────────────────────────────────────────

async def run_mcp(config: Config, transport: str = "stdio", port: int = 8090) -> None:
    global _driver, _config

    _config = config

    # Connect to already-running Chrome
    _driver = CDPDriver(cdp_port=config.chrome.cdp_port)
    try:
        await _driver.connect()
    except Exception as e:
        logger.error(
            "Cannot connect to Chrome on CDP port %d. "
            "Run 'chatgpt-web2api' first to start Chrome. Error: %s",
            config.chrome.cdp_port, e
        )
        # Send error via MCP and exit cleanly
        return

    server = create_server()
    init_options = server.create_initialization_options()

    try:
        if transport == "stdio":
            async with stdio_server() as (read, write):
                await server.run(read, write, init_options)
        elif transport == "sse":
            await _run_sse(server, init_options, config, port)
    finally:
        await _driver.close()


async def _run_sse(server: Server, init_options, config: Config, port: int) -> None:
    """Run MCP server with SSE transport for remote/web clients."""
    from mcp.server.sse import SseServerTransport
    from aiohttp import web

    sse = SseServerTransport("/messages")

    async def handle_sse(request: web.Request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(streams[0], streams[1], init_options)
        return web.Response()

    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.router.add_get("/sse", handle_sse)
    app.router.add_post("/messages", sse.handle_post_message)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, port)
    await site.start()
    logger.info("MCP SSE server on http://%s:%d/sse", config.server.host, port)

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


# ── CLI ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chatgpt-web2api-mcp",
        description="MCP server for ChatGPT-Web2API",
    )
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport layer (default: stdio)")
    parser.add_argument("--port", type=int, default=8090, help="SSE port (default: 8090)")
    parser.add_argument("--cdp-port", type=int, help="Chrome CDP port (default: from config)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # MCP stdio requires stdout for protocol only
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)

    config = Config.load(args.config)
    if args.cdp_port:
        config.chrome.cdp_port = args.cdp_port

    try:
        asyncio.run(run_mcp(config, transport=args.transport, port=args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
