# API Reference

ChatGPT-Web2API exposes two interfaces: an OpenAI-compatible REST API and an MCP server.

## REST API

Base URL: `http://localhost:8080/v1`

### Chat Completions

```
POST /v1/chat/completions
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | yes | Model slug (see `/v1/models`). Use `"auto"` for default. |
| `messages` | array | yes | Array of `{"role": "user"/"assistant", "content": "..."}` |
| `stream` | boolean | no | Enable SSE streaming (default: `false`) |
| `temperature` | float | no | Ignored — ChatGPT controls this |
| `max_tokens` | int | no | Ignored — ChatGPT controls this |

**Response (non-streaming):**

```json
{
  "id": "conv-abc123",
  "object": "chat.completion",
  "model": "auto",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help?"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

**Response (streaming):**

```
data: {"id":"conv-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"conv-abc123","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Models

```
GET /v1/models
```

Returns available ChatGPT models:

```json
{
  "object": "list",
  "data": [
    {"id": "auto", "object": "model", "owned_by": "chatgpt"},
    {"id": "gpt-5-5", "object": "model", "owned_by": "chatgpt"}
  ]
}
```

## MCP Tools

### Chat & Completion

| Tool | Input | Output |
|------|-------|--------|
| `chat_completion` | `message`, `system_prompt?`, `model?`, `conversation_id?`, `project_id?` | Response text + metadata |
| `chat_with_gpt` | `gpt_id`, `message` | Response text |

### Read Operations

| Tool | Input | Output |
|------|-------|--------|
| `list_models` | — | Model catalog |
| `list_projects` | — | Project list with IDs |
| `list_conversations` | `limit?`, `offset?` | Conversation list |
| `get_conversation` | `conversation_id` | Full message tree |
| `list_memories` | — | Memory list with IDs |
| `list_gpts` | — | Custom GPT catalog |
| `list_project_files` | `project_id` | File listing |

### Write Operations

| Tool | Input | Output |
|------|-------|--------|
| `create_project` | `name` | Project ID |
| `update_project_instructions` | `project_id`, `instructions` | Confirmation |
| `create_memory` | `content` | Confirmation |
| `archive_conversation` | `conversation_id`, `archive` | Confirmation |
| `delete_conversation` | `conversation_id` | Confirmation |
| `delete_memory` | `memory_id` | Confirmation |

## Model Mapping

The API maps common OpenAI model names to ChatGPT web equivalents:

| Requested | Maps to |
|-----------|---------|
| `auto` | ChatGPT default (reasoning model) |
| `gpt-4o` | `auto` |
| `gpt-4` | `gpt-5` |
| `gpt-3.5-turbo` | `gpt-5-mini` |

Use `list_models` for the current live catalog.

## Error Handling

All errors return standard OpenAI-compatible format:

```json
{
  "error": {
    "message": "Chrome not connected. Start chatgpt-web2api first.",
    "type": "connection_error",
    "code": "chrome_disconnected"
  }
}
```

Common error codes:

| Code | Meaning |
|------|---------|
| `chrome_disconnected` | Chrome process not running or CDP port unreachable |
| `timeout` | ChatGPT did not respond within the timeout window |
| `navigation_failed` | Could not navigate to chatgpt.com |
| `login_required` | ChatGPT session expired — re-login needed |
