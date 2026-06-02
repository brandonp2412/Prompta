# ChatGPT-Web2API

OpenAI-compatible API proxy that routes through the real ChatGPT web interface via Chrome DevTools Protocol.

**No API key needed. No sentinel solving. Works with your ChatGPT Plus account.**

## How It Works

```
Client (OpenAI SDK / curl)
  ↓ HTTP (aiohttp)
API Server (:8080)
  ↓ CDP (websockets)
Chrome (chatgpt.com)
```

The proxy automates a real Chrome browser to send messages and read responses. The browser handles all anti-bot challenges (Turnstile, PoW, so) automatically — just like a real user.

## Quick Start

### 1. Start Chrome with remote debugging

Close all Chrome instances, then:

```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

Navigate to `https://chatgpt.com` and log in.

### 2. Install and run the proxy

```bash
pip install -e .
chatgpt-web2api --cdp-port 9222
```

### 3. Use it like the OpenAI API

```bash
# Non-streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello!"}]}'

# Streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"Hello!"}]}'

# List models
curl http://localhost:8080/v1/models

# List projects
curl http://localhost:8080/v1/projects
```

### 4. Use with OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

# Non-streaming
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Streaming
for chunk in client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completion (streaming + non-streaming) |
| `/v1/models` | GET | Model catalog from ChatGPT |
| `/v1/projects` | GET | ChatGPT projects list |
| `/health` | GET | Health check |

## Models

Available models (auto-detected from your ChatGPT account):

| Model ID | Description |
|----------|-------------|
| `auto` | Default model selection |
| `gpt-5-5` | GPT-5.5 |
| `gpt-5-3` | GPT-5.3 |
| `gpt-5-mini` | GPT-5 Mini |
| `gpt-5.3-mini` | GPT-5.3 Mini |

## Project Memory

Use ChatGPT projects for persistent context:

```python
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_body={"project_id": "g-p-abc123"}  # ChatGPT project gizmo_id
)
```

## Architecture

- **CDP Driver** (`cdp_driver.py`) — Automates Chrome via DevTools Protocol
  - Connects to Chrome's CDP websocket
  - Types messages via `Input.insertText`
  - Clicks send via JS `MouseEvent` sequence
  - Reads responses via conversation API
  
- **API Server** (`api_server.py`) — OpenAI-compatible HTTP server
  - `aiohttp` based, streaming SSE support
  - Request serialization (one at a time)
  - Model name mapping

## Performance

Typical latency (ChatGPT Plus):
- Page navigation: ~2-5s
- Message typing + send: ~0.5s
- Response generation: 3-30s (depends on model + output length)
- Total end-to-end: ~13-36s

## Requirements

- Python 3.11+
- Chrome with remote debugging enabled
- ChatGPT Plus account (logged in)
- Dependencies: `websockets`, `aiohttp`

## License

MIT
