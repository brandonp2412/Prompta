# ChatGPT-Web2API

OpenAI-compatible API proxy that drives a real ChatGPT browser session via Chrome DevTools Protocol.

**No API key. No sentinel solving. One command to start.**

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────┐    CDP     ┌──────────────┐
│  Your code   │ ────────────► │  API Server  │ ─────────► │    Chrome     │
│  (SDK/curl)  │ ◄──────────── │  (aiohttp)   │ ◄───────── │  chatgpt.com  │
└──────────────┘   JSON/SSE    └──────────────┘  commands  └──────────────┘
```

The proxy launches and owns a dedicated Chrome instance. It types messages, clicks send, and reads responses — exactly like a human would. All anti-bot challenges (Turnstile, PoW, so) are handled automatically by the browser.

## Quick Start

```bash
# Install
pip install -e .

# Start (launches Chrome + API server)
chatgpt-web2api

# Or with options
chatgpt-web2api --port 9090 --log-level DEBUG
```

On first run, Chrome opens to `chatgpt.com` — **log in with your account**. The proxy waits until it detects a valid auth session, then the API is live.

Subsequent starts reuse the saved Chrome profile (already logged in).

## Usage

```bash
# Chat completion
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello!"}]}'

# Streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"Hello!"}]}'

# Models
curl http://localhost:8080/v1/models

# Projects
curl http://localhost:8080/v1/projects
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

# Non-streaming
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is 2+2?"}]
)
print(resp.choices[0].message.content)  # "4"

# Streaming
for chunk in client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True,
):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# With project memory
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_body={"project_id": "g-p-abc123"}
)
```

## Configuration

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | — | Path to config JSON |
| `--port` | 8080 | API server port |
| `--host` | 127.0.0.1 | API server host |
| `--cdp-port` | 9222 | Chrome CDP port |
| `--chrome-path` | auto | Path to Chrome binary |
| `--user-data-dir` | `~/.chatgpt-web2api/chrome-profile` | Chrome profile dir |
| `--headless` | false | Run Chrome headless |
| `--log-level` | INFO | Logging level |

### Config File

```json
{
  "port": 8080,
  "host": "127.0.0.1",
  "cdp_port": 9222,
  "chrome_path": "auto",
  "user_data_dir": "~/.chatgpt-web2api/chrome-profile",
  "headless": false,
  "default_model": "auto",
  "api_keys": [],
  "request_timeout": 120
}
```

### Environment Variables

All config keys are available as `W2A_*` env vars:

```bash
W2A_PORT=9090 W2A_LOG_LEVEL=DEBUG chatgpt-web2api
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completion (streaming + non-streaming) |
| GET | `/v1/models` | Model catalog from ChatGPT |
| GET | `/v1/projects` | ChatGPT projects list |
| GET | `/health` | Health + Chrome status |

## Models

Live models from your ChatGPT account. Aliases for backward compatibility:

| Alias | Maps to |
|-------|---------|
| `gpt-4o` | `auto` |
| `gpt-4` | `gpt-5` |
| `gpt-3.5-turbo` | `gpt-5-mini` |

## Project Memory

Use ChatGPT Projects for persistent context:

```python
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_body={"project_id": "g-p-abc123"}
)
```

## How It Works

1. **Chrome lifecycle** — The service finds or launches a Chrome instance with `--remote-debugging-port`. A dedicated user data dir keeps the proxy's Chrome separate from your daily browser.

2. **CDP driver** — Connects to Chrome via WebSocket. Types messages with `Input.insertText`, clicks send via JS `MouseEvent` sequence (bypasses React synthetic events).

3. **Response retrieval** — Hybrid approach: polls DOM for streaming text, then fetches the final response from ChatGPT's conversation API (`/backend-api/conversation/{id}`). This handles thinking models where the DOM is empty during the reasoning phase.

4. **API server** — Standard aiohttp server with OpenAI-compatible JSON schema. Requests are serialized (one at a time through the single browser). SSE streaming support.

5. **Health monitoring** — Background task pings Chrome CDP every 30s. Auto-restart on crash.

## Requirements

- Python 3.11+
- Chrome or Chromium installed
- ChatGPT Plus account
- Dependencies: `websockets`, `aiohttp`

## License

MIT
