# Changelog

All notable changes to ChatGPT-Web2API will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-06-06

### Added
- **MCP Server** — expose ChatGPT as an MCP server with 15 tools, resources, and prompts for AI agents
- **15 MCP tools**: chat_completion, list_models, list_projects, list_conversations, get_conversation, delete_conversation, archive_conversation, create_project, update_project_instructions, list_project_files, list_memories, create_memory, delete_memory, list_gpts, chat_with_gpt
- **Prompt argument completion** — autocomplete project names in MCP prompts
- **Memory management** — list (41 memories via `/backend-api/memories`), create (via chat), delete
- **Custom GPT interaction** — list and chat with Custom GPTs
- **Project file listing** — read files attached to ChatGPT projects
- **Archive/unarchive conversations** — reversible alternative to delete
- **Token auto-refresh** — proactive JWT refresh via `ensure_token()`
- **Source guide** (`guide.md`) — teaches AI agents ChatGPT's mental model
- **Rich tool descriptions** — domain knowledge baked into every MCP tool description
- **Output schemas** — structured output on all tools following Memory server pattern
- **Pydantic input validation** — BaseModel schemas for all tool inputs
- **Tool name enum** — prevents string typos in tool routing
- **Resource templates** — dynamic URI templates for project resources
- **Docker deployment** with cookie injection
- **First-run login flow** — auto-detects when user needs to log in
- **Deployment guide** at `docs/deployment.md`
- **Protocol reference** at `docs/protocol-reference.md`

### Changed
- Refactored MCP server to follow official `modelcontextprotocol/servers` patterns
- CDP driver now has 24 methods (was 6)
- All MCP tools have full ToolAnnotations with all 4 hints

### Tested
- Live tested against ChatGPT Plus account: 13/13 tools pass
- 17 models, 50 projects, 41 memories verified
- Chat completion: "8+7?" → "15", multi-turn "×3" → "45"
- Archive + unarchive round-trip verified
- Memory DELETE verified (200 OK)

## [0.1.0] - 2025-06-04

### Added
- Initial release — CDP-driven proxy with OpenAI-compatible API
- Chrome lifecycle management (launch, attach, monitor, restart)
- Message input via `Input.insertText` + JS `MouseEvent` sequence
- Response retrieval via DOM polling + conversation API hybrid
- Streaming SSE support
- Multi-turn conversation continuity
- System prompts via text prepend
- OpenAI Python SDK compatibility
- 19/19 end-to-end tests pass
- 6 clean modules, 1,314 lines
