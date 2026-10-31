# Architecture

| Service | Responsibility |
| --- | --- |
| `prompta-ui` | Job management, local Chats view, durable user-clicked reply enqueue |
| `prompta-scheduler` | Due times and durable delivery enqueue |
| `prompta-delivery-worker` | Fresh-chat dispatch, passive capture, historical recovery |
| `prompta-manual-reply-worker` | Explicit replies to verified branches and their captures |
| `prompta-browser` | Authenticated Chromium/CDP session |
| `prompta-connector-approval-watch` | Opt-in connector permission supervision |
| `prompta-browser-watchdog.timer` | Independent cleanup of idle owned tabs |

`prompta.target` groups the application services.

## Runs and replies

The scheduler queues due jobs. The delivery worker opens a fresh ChatGPT tab, confirms prompt acceptance, and captures the final response from that tab's conversation POST or semantic DOM changes. Captures run independently and require explicit completion evidence. Verified response changes refresh the tab's activity clock; the watchdog reaps owned tabs after 45 minutes of inactivity.

Clicking Send durably queues a reply to the stored conversation and parent. The worker verifies the exact branch, recovering its latest parent when needed. Failed verification preserves the draft for another attempt or an explicit **Continue in new chat** action. A Send on a run lacking a conversation ID creates a fresh chat with its saved transcript and available original images.

Each idempotency key identifies one immutable payload. Uncertain local receipts retain that key. Ambiguous ChatGPT submissions end in `outcome_unknown` for user review. Prepared reply intents remain local until explicit dispatch.

## Storage and updates

Private SQLAlchemy SQLite WAL stores hold queue state, per-send prompts, final assistant text, bounded/redacted tool summaries, completion status, and branch identity. Image bytes use private hashed files with SQLite metadata. State lives under `~/.local/state/prompta/`; directories use mode 0700 and database/WAL files use 0600. Logs contain operational metadata. Tool details appear in the owner-local transcript.

Chats listing, search, and refresh read local storage. A shared `/api/events` EventSource sends `sync`, `jobs`, and `chats` invalidations; local GET endpoints provide the data. The stream has 15-second heartbeats, automatic reconnection, and a 60-second visible-tab fallback refresh. Stable Svelte component and list identities preserve navigation, drafts, and scroll state.

## Response recovery

Live recovery reads the installed observer in the same owned tab every 45 seconds within its activity lease. Historical recovery selects interrupted or unavailable local runs with a verified conversation UUID and an expired capture lease. It opens that exact conversation in a temporary read-only tab, verifies the route and original prompt, and captures visible assistant output. Completion requires a rendered Copy action with generation finished. Completed records stay immutable.

Historical navigation is globally paced to 90 seconds. Per-chat retry delays grow from 90 seconds to one hour. HTTP 429 responses trigger persisted read backoff starting at five minutes, doubling to a 30-minute cap with jitter and support for longer `Retry-After` values. Security challenges pause reads for 30 minutes. Delivery admission and read backoff use separate gates.
