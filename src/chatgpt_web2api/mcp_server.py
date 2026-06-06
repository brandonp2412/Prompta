"""MCP Server — expose ChatGPT-Web2API as an MCP server for AI agents.

Implements the Model Context Protocol following official reference patterns
from the `modelcontextprotocol/servers` repository:

  - Pydantic BaseModel input schemas (mcp-server-git pattern)
  - Enum for tool names to prevent typos
  - ToolAnnotations on every tool with all 4 hints
  - outputSchema + structuredContent on every tool
  - Resource templates for dynamic URIs
  - Prompt argument completion support
  - Pure business logic with thin tool handlers
  - raise_exceptions=True for proper error propagation
  - Input validation via SDK (validate_input=True)

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
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .config import Config
from .cdp_driver import CDPDriver

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Input Schemas — Pydantic BaseModel (official pattern from mcp-server-git)
# ═══════════════════════════════════════════════════════════════

class ChatCompletionInput(BaseModel):
    """Input schema for chat_completion tool."""
    message: str = Field(description="The user message to send to ChatGPT")
    system_prompt: Optional[str] = Field(
        default=None,
        description=(
            "System instructions prepended to the message. "
            "Changes to this value start a new conversation."
        ),
    )
    model: str = Field(
        default="auto",
        description="Model slug: auto, gpt-5, gpt-5-mini, etc.",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID of an existing conversation to continue. "
            "Omit to start a new chat or auto-continue."
        ),
    )
    project_id: Optional[str] = Field(
        default=None,
        description=(
            "ChatGPT project gizmo ID (e.g. g-p-abc123) "
            "for project-scoped persistent memory and instructions"
        ),
    )


class ListModelsInput(BaseModel):
    """No inputs needed — empty schema."""
    pass


class ListProjectsInput(BaseModel):
    """No inputs needed — empty schema."""
    pass


class GetConversationInput(BaseModel):
    """Input for retrieving conversation history."""
    conversation_id: str = Field(
        description="UUID of the conversation to retrieve",
    )


# ═══════════════════════════════════════════════════════════════
# Tool Name Enum — prevents typos (official pattern from mcp-server-git)
# ═══════════════════════════════════════════════════════════════

class ToolName(str, Enum):
    CHAT_COMPLETION = "chat_completion"
    LIST_MODELS = "list_models"
    LIST_PROJECTS = "list_projects"
    GET_CONVERSATION = "get_conversation"


# ═══════════════════════════════════════════════════════════════
# Output Schemas — structured output validation (Memory server pattern)
# ═══════════════════════════════════════════════════════════════

CHAT_COMPLETION_OUTPUT = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "The assistant response text"},
        "model": {"type": "string", "description": "Model used for generation"},
        "conversation_id": {
            "type": "string",
            "description": "UUID of the conversation (for multi-turn)",
        },
    },
    "required": ["content", "model", "conversation_id"],
}

MODEL_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
    },
    "required": ["id", "title"],
}

LIST_MODELS_OUTPUT = {
    "type": "object",
    "properties": {
        "models": {
            "type": "array",
            "items": MODEL_ITEM,
        },
    },
    "required": ["models"],
}

PROJECT_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "memory_scope": {"type": "string"},
    },
    "required": ["id", "name"],
}

LIST_PROJECTS_OUTPUT = {
    "type": "object",
    "properties": {
        "projects": {
            "type": "array",
            "items": PROJECT_ITEM,
        },
    },
    "required": ["projects"],
}

GET_CONVERSATION_OUTPUT = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["role", "content"],
            },
        },
    },
    "required": ["id"],
}


# ═══════════════════════════════════════════════════════════════
# Global State
# ═══════════════════════════════════════════════════════════════

_driver: CDPDriver | None = None
_config: Config | None = None


# ═══════════════════════════════════════════════════════════════
# Business Logic — pure functions (official pattern from mcp-server-git)
# ═══════════════════════════════════════════════════════════════

async def do_chat_completion(driver: CDPDriver, args: dict, config: Config) -> dict:
    """Execute a chat completion through the CDP driver.

    Returns a dict with structured output matching CHAT_COMPLETION_OUTPUT.
    """
    # Validate with Pydantic
    validated = ChatCompletionInput(**args)
    message = validated.message
    system_prompt = validated.system_prompt
    model = validated.model
    conversation_id = validated.conversation_id
    project_id = validated.project_id or (
        config.chatgpt.default_project_id if config else None
    )

    # Build the full text
    if system_prompt:
        full_text = f"[System Instructions]\n{system_prompt}\n\n[User]\n{message}"
    else:
        full_text = message

    # Navigate to correct conversation
    if conversation_id:
        await driver.navigate_conversation(conversation_id)
    elif driver._current_conv_id and not system_prompt and not project_id:
        # Auto-continue existing conversation
        logger.info("Auto-continuing conversation: %s", driver._current_conv_id)
    else:
        await driver.navigate_new_chat(gizmo_id=project_id)

    # Send and collect response
    full_response = ""
    conv_id = ""
    async for chunk in driver.send_and_stream(full_text, timeout=120):
        if chunk.delta:
            full_response += chunk.delta
        if chunk.finish_reason:
            conv_id = driver._current_conv_id or ""

    return {
        "content": full_response,
        "model": model,
        "conversation_id": conv_id,
    }


async def do_list_models(driver: CDPDriver) -> dict:
    """List available models. Returns dict matching LIST_MODELS_OUTPUT."""
    models = await driver.get_models()
    return {
        "models": [
            {"id": m.get("slug", ""), "title": m.get("title", "")}
            for m in models
        ],
    }


async def do_list_projects(driver: CDPDriver) -> dict:
    """List available projects. Returns dict matching LIST_PROJECTS_OUTPUT."""
    projects = await driver.get_projects()
    return {
        "projects": [
            {
                "id": p.get("id", ""),
                "name": p.get("name", "Unknown"),
                "memory_scope": p.get("memory_scope", "project_v2"),
            }
            for p in projects
            if p.get("id")
        ],
    }


async def do_get_conversation(driver: CDPDriver, args: dict) -> dict:
    """Retrieve conversation history. Returns dict matching GET_CONVERSATION_OUTPUT."""
    validated = GetConversationInput(**args)
    data = await driver.get_conversation(validated.conversation_id)

    # Extract messages from conversation mapping
    messages = []
    mapping = data.get("mapping", {})
    current_node = data.get("current_node")

    # Walk the conversation tree from current_node backwards
    node_id = current_node
    chain = []
    visited = set()
    while node_id and node_id not in visited:
        visited.add(node_id)
        node_data = mapping.get(node_id, {})
        msg = node_data.get("message")
        if msg and msg.get("content"):
            role = msg.get("author", {}).get("role", "unknown")
            # Extract text from content parts
            parts = msg.get("content", {}).get("parts", [])
            text = " ".join(
                p for p in parts if isinstance(p, str)
            )
            if text and role in ("user", "assistant"):
                chain.append({"role": role, "content": text})
        node_id = node_data.get("parent")

    chain.reverse()
    messages = chain

    return {
        "id": data.get("id", validated.conversation_id),
        "title": data.get("title", ""),
        "messages": messages[:50],  # Cap at 50 messages
    }


# ═══════════════════════════════════════════════════════════════
# Tool Definitions — declarative list with full annotations
# ═══════════════════════════════════════════════════════════════

def _build_tools() -> list[mcp_types.Tool]:
    """Build the list of tool definitions with full annotations and output schemas."""
    return [
        mcp_types.Tool(
            name=ToolName.CHAT_COMPLETION.value,
            title="ChatGPT Completion",
            description=(
                "Send a message to ChatGPT and get a response. "
                "Supports multi-turn conversation via conversation_id. "
                "Supports project-scoped persistent memory via project_id."
            ),
            inputSchema=ChatCompletionInput.model_json_schema(),
            outputSchema=CHAT_COMPLETION_OUTPUT,
            annotations=mcp_types.ToolAnnotations(
                title="ChatGPT Completion",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        mcp_types.Tool(
            name=ToolName.LIST_MODELS.value,
            title="List Models",
            description="List all ChatGPT models available on the account",
            inputSchema=ListModelsInput.model_json_schema(),
            outputSchema=LIST_MODELS_OUTPUT,
            annotations=mcp_types.ToolAnnotations(
                title="List Models",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        mcp_types.Tool(
            name=ToolName.LIST_PROJECTS.value,
            title="List Projects",
            description=(
                "List ChatGPT projects. Each project has persistent memory, "
                "custom instructions, and file attachments."
            ),
            inputSchema=ListProjectsInput.model_json_schema(),
            outputSchema=LIST_PROJECTS_OUTPUT,
            annotations=mcp_types.ToolAnnotations(
                title="List Projects",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        mcp_types.Tool(
            name=ToolName.GET_CONVERSATION.value,
            title="Get Conversation",
            description="Retrieve the full message history of a conversation by ID",
            inputSchema=GetConversationInput.model_json_schema(),
            outputSchema=GET_CONVERSATION_OUTPUT,
            annotations=mcp_types.ToolAnnotations(
                title="Get Conversation",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
    ]


# ═══════════════════════════════════════════════════════════════
# Server Factory
# ═══════════════════════════════════════════════════════════════

def create_server() -> Server:
    """Create and configure the MCP server with all capabilities."""

    server = Server("chatgpt-web2api")

    # ── Tools (model-controlled) ──────────────────────────────

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return _build_tools()

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> tuple[list[mcp_types.TextContent], dict] | list[mcp_types.TextContent] | dict:
        """Route tool calls to business logic functions.

        Returns:
            - dict → structured content only (SDK wraps in text + structuredContent)
            - list → unstructured content only
            - tuple(list, dict) → both unstructured + structured content
        """
        if _driver is None:
            raise ConnectionError(
                "Not connected to Chrome. Run 'chatgpt-web2api' first."
            )

        if name == ToolName.CHAT_COMPLETION.value:
            result = await do_chat_completion(_driver, arguments, _config)
            text_content = [mcp_types.TextContent(type="text", text=result["content"])]
            return text_content, result

        elif name == ToolName.LIST_MODELS.value:
            result = await do_list_models(_driver)
            return result

        elif name == ToolName.LIST_PROJECTS.value:
            result = await do_list_projects(_driver)
            return result

        elif name == ToolName.GET_CONVERSATION.value:
            result = await do_get_conversation(_driver, arguments)
            return result

        else:
            raise ValueError(f"Unknown tool: {name}")

    # ── Resources (application-controlled) ────────────────────

    @server.list_resources()
    async def list_resources() -> list[mcp_types.Resource]:
        """List static resources — models and account info."""
        resources = [
            mcp_types.Resource(
                uri="chatgpt://models",
                name="Available Models",
                description="All ChatGPT model slugs available on the account",
                mimeType="application/json",
            ),
            mcp_types.Resource(
                uri="chatgpt://account",
                name="Account Info",
                description="Current ChatGPT account status and user info",
                mimeType="application/json",
            ),
        ]

        # Add project resources dynamically
        if _driver:
            try:
                projects = await _driver.get_projects()
                for p in projects:
                    if p.get("id"):
                        resources.append(
                            mcp_types.Resource(
                                uri=f"chatgpt://projects/{p['id']}",
                                name=p.get("name", "Unknown Project"),
                                description=(
                                    f"ChatGPT project: {p.get('name', 'Unknown')} "
                                    f"({p.get('memory_scope', 'project_v2')} memory)"
                                ),
                                mimeType="application/json",
                            )
                        )
            except Exception as e:
                logger.warning("Failed to list project resources: %s", e)

        return resources

    @server.list_resource_templates()
    async def list_resource_templates() -> list[mcp_types.ResourceTemplate]:
        """Declare URI templates for dynamic resource access."""
        return [
            mcp_types.ResourceTemplate(
                uriTemplate="chatgpt://projects/{project_id}",
                name="ChatGPT Project",
                description="Access a specific ChatGPT project by ID",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(
        request: mcp_types.ReadResourceRequest,
    ) -> str | list[mcp_types.ResourceContents]:
        """Read a specific resource by URI."""
        uri = str(request.params.uri)

        if _driver is None:
            raise ConnectionError("Not connected to Chrome")

        # Static resources
        if uri == "chatgpt://models":
            models = await _driver.get_models()
            data = [
                {"id": m.get("slug", ""), "title": m.get("title", "")}
                for m in models
            ]
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif uri == "chatgpt://account":
            return json.dumps(
                {
                    "user": _driver._user_name,
                    "connected": _driver.is_connected,
                },
                ensure_ascii=False,
                indent=2,
            )

        # Dynamic project resources
        elif uri.startswith("chatgpt://projects/"):
            project_id = uri.split("/")[-1]
            projects = await _driver.get_projects()
            for p in projects:
                if p.get("id") == project_id:
                    return json.dumps(p, ensure_ascii=False, indent=2)
            raise ValueError(f"Project not found: {project_id}")

        raise ValueError(f"Unknown resource URI: {uri}")

    # ── Prompts (user-controlled) ─────────────────────────────

    @server.list_prompts()
    async def list_prompts() -> list[mcp_types.Prompt]:
        return [
            mcp_types.Prompt(
                name="ask-chatgpt",
                description=(
                    "Send a question to ChatGPT with optional project context. "
                    "The model will use the chat_completion tool to get an answer."
                ),
                arguments=[
                    mcp_types.PromptArgument(
                        name="question",
                        description="The question to ask",
                        required=True,
                    ),
                    mcp_types.PromptArgument(
                        name="project",
                        description=(
                            "Project name or ID for scoped memory "
                            "(optional — uses default project if omitted)"
                        ),
                        required=False,
                    ),
                ],
            ),
            mcp_types.Prompt(
                name="continue-chat",
                description=(
                    "Continue the last conversation with a follow-up message. "
                    "Automatically uses the active conversation context."
                ),
                arguments=[
                    mcp_types.PromptArgument(
                        name="message",
                        description="Follow-up message to send",
                        required=True,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(
        request: mcp_types.GetPromptRequest,
    ) -> mcp_types.GetPromptResult:
        name = request.params.name
        args = request.params.arguments or {}

        if name == "ask-chatgpt":
            question = args.get("question", "")
            project = args.get("project", "")
            if not question:
                raise ValueError("question argument is required")

            tool_args: dict[str, Any] = {"message": question}

            # Resolve project name → ID
            if project and _driver:
                try:
                    projects = await _driver.get_projects()
                    for p in projects:
                        if project.lower() in (
                            p.get("name", "").lower(),
                            p.get("id", "").lower(),
                        ):
                            tool_args["project_id"] = p["id"]
                            break
                except Exception as e:
                    logger.warning("Project resolution failed: %s", e)

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


# ═══════════════════════════════════════════════════════════════
# Transport Layer
# ═══════════════════════════════════════════════════════════════


async def run_mcp(
    config: Config, transport: str = "stdio", port: int = 8090
) -> None:
    """Connect to Chrome and run the MCP server."""
    global _driver, _config

    _config = config

    # Connect to already-running Chrome
    _driver = CDPDriver(cdp_port=config.chrome.cdp_port)
    try:
        await _driver.connect()
        logger.info(
            "Connected to Chrome on CDP port %d", config.chrome.cdp_port
        )
    except Exception as e:
        logger.error(
            "Cannot connect to Chrome on CDP port %d. "
            "Run 'chatgpt-web2api' first to start Chrome. Error: %s",
            config.chrome.cdp_port,
            e,
        )
        return

    server = create_server()
    init_options = server.create_initialization_options()

    try:
        if transport == "stdio":
            async with stdio_server() as (read, write):
                # raise_exceptions=True — official pattern for proper error propagation
                await server.run(read, write, init_options, raise_exceptions=True)
        elif transport == "sse":
            await _run_sse(server, init_options, config, port)
    finally:
        await _driver.close()


async def _run_sse(
    server: Server, init_options, config: Config, port: int
) -> None:
    """Run MCP server with SSE transport for remote/web clients."""
    from mcp.server.sse import SseServerTransport
    from aiohttp import web

    sse = SseServerTransport("/messages")

    async def handle_sse(request: web.Request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], init_options, raise_exceptions=True
            )
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


# ═══════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chatgpt-web2api-mcp",
        description="MCP server for ChatGPT-Web2API",
    )
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport layer (default: stdio)",
    )
    parser.add_argument(
        "--port", type=int, default=8090, help="SSE port (default: 8090)"
    )
    parser.add_argument(
        "--cdp-port", type=int, help="Chrome CDP port (default: from config)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
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
