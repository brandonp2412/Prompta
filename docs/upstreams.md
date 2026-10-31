# Upstreams

Prompta's Git upstream is [Octo-Lex/ChatGPT-Web2API](https://github.com/Octo-Lex/ChatGPT-Web2API), configured as the `upstream` remote.

Browser compatibility references:

| Repository | Source revision | Reference |
| --- | --- | --- |
| [stufently/gpt-web-gateway](https://github.com/stufently/gpt-web-gateway) | [945182a](https://github.com/stufently/gpt-web-gateway/tree/945182a) | `src/lib/conversation-read.js`, `src/chatgpt.js`: SSE formats and passive interception |
| [qayshp/chatgpt-playwright-backend](https://github.com/qayshp/chatgpt-playwright-backend) | [85b930e](https://github.com/qayshp/chatgpt-playwright-backend/tree/85b930e) | `src/dom-runtime.js`: semantic message IDs, Markdown, completion controls, MutationObserver |
| [FirstWari/chatgpt-web](https://github.com/FirstWari/chatgpt-web) | [86383d5](https://github.com/FirstWari/chatgpt-web/tree/86383d5) | `chatgpt_web/selectors.py`, `chatgpt_web/chat.py`: selectors and completion hints |

Installed dependencies are declared in [pyproject.toml](../pyproject.toml) and [package.json](../package.json), with versions resolved in `uv.lock` and `bun.lock`.
