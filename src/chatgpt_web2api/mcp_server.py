"""MCP Server — expose ChatGPT-Web2API as an MCP tool.

Run:
    chatgpt-web2api-mcp                    # stdio (default)
    chatgpt-web2api-mcp --transport sse    # SSE on port 8090

Tools exposed:
    chat_completion — send a message, get a response
    list_models     — list available ChatGPT models
    list_projects   — list ChatGPT projects
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

# Global state
_driver: CDPDriver | None = None
_config: Config | None = None


def create_server() -> Server:
    server = Server("chatgpt-web2api")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name="chat_completion",
                title="ChatGPT Completion",
                description=(
                    "Send a message to ChatGPT and get a response. "
                    "Supports multi-turn conversation via conversation_id. "
                    "Supports project-scoped memory via project_id."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The user message to send",
                        },
                        "system_prompt": {
                            "type": "string",
                            "description": "Optional system instructions prepended to the message",
                        },
                        "model": {
                            "type": "string",
                            "description": "Model to use (auto, gpt-5-5, gpt-5-mini, etc.)",
                            "default": "auto",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Continue an existing conversation. Omit for new chat.",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "ChatGPT project gizmo ID (e.g. g-p-abc123) for persistent memory",
                        },
                    },
                    "required": ["message"],
                },
            ),
            mcp_types.Tool(
                name="list_models",
                title="List ChatGPT Models",
                description="List available ChatGPT models from the account",
                inputSchema={"type": "object", "properties": {}},
            ),
            mcp_types.Tool(
                name="list_projects",
                title="List ChatGPT Projects",
                description="List ChatGPT projects with persistent memory",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(request: mcp_types.CallToolRequest) -> list[mcp_types.TextContent]:
        global _driver, _config

        name = request.params.name
        args = request.params.arguments or {}

        if _driver is None:
            return [mcp_types.TextContent(type="text", text="Error: not connected to Chrome")]

        try:
            if name == "chat_completion":
                return await _handle_chat(args)
            elif name == "list_models":
                return await _handle_models()
            elif name == "list_projects":
                return await _handle_projects()
            else:
                return [mcp_types.TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error("Tool error: %s", e, exc_info=True)
            return [mcp_types.TextContent(type="text", text=f"Error: {e}")]

    return server


async def _handle_chat(args: dict) -> list[mcp_types.TextContent]:
    global _driver

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
    elif conversation_id is None and _driver._current_conv_id and not system_prompt:
        # Continue existing conversation
        pass
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
    global _driver
    models = await _driver.get_models()
    data = [{"id": m.get("slug", ""), "title": m.get("title", "")} for m in models]
    return [mcp_types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]


async def _handle_projects() -> list[mcp_types.TextContent]:
    global _driver
    projects = await _driver.get_projects()
    return [mcp_types.TextContent(type="text", text=json.dumps(projects, ensure_ascii=False))]


async def run_mcp(config: Config, transport: str = "stdio", port: int = 8090) -> None:
    global _driver, _config

    _config = config

    # Connect to already-running Chrome (MCP assumes chatgpt-web2api is already running)
    _driver = CDPDriver(cdp_port=config.chrome.cdp_port)
    try:
        await _driver.connect()
    except RuntimeError as e:
        if "No access token" in str(e):
            logger.error(
                "Not logged in. Run 'chatgpt-web2api' first to start Chrome and log in, "
                "then run 'chatgpt-web2api-mcp' to start the MCP server."
            )
            return
        raise
    except Exception as e:
        logger.error(
            "Cannot connect to Chrome on CDP port %d. "
            "Run 'chatgpt-web2api' first to start Chrome. Error: %s",
            config.chrome.cdp_port, e
        )
        return

    server = create_server()

    if transport == "stdio":
        async with stdio_server() as (read, write):
            await server.run(
                read, write,
                server.create_initialization_options(),
            )
    elif transport == "sse":
        from mcp.server.sse import SseServerTransport
        from aiohttp import web

        sse = SseServerTransport("/messages")

        async def handle_sse(request: web.Request) -> web.StreamResponse:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1],
                    server.create_initialization_options(),
                )
            return web.Response()

        app = web.Application()
        app.router.add_get("/sse", handle_sse)
        app.router.add_post("/messages", sse.handle_post_message)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server.host, port)
        await site.start()
        logger.info("MCP SSE server on http://%s:%d/sse", config.server.host, port)

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    await _driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chatgpt-web2api-mcp",
        description="MCP server for ChatGPT-Web2API",
    )
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8090, help="SSE port")
    parser.add_argument("--cdp-port", type=int, help="Chrome CDP port")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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
