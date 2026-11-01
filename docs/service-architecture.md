# Architecture

| Service | Responsibility |
| --- | --- |
| `prompta-ui` | Job management, local Chats view, durable user-clicked reply enqueue |
| `prompta-scheduler` | Due times and durable delivery enqueue |
| `prompta-delivery-worker` | Fresh-chat dispatch, passive capture, historical recovery |
| `prompta-manual-reply-worker` | Explicit replies to verified branches and their captures |
| `prompta-browser` | Authenticated Chromium/CDP session |
| `prompta-browser-watchdog.timer` | Independent cleanup of idle owned tabs |

`prompta.target` groups the application services.

## Guarded production deployments

On Nox, update production using `./.venv/bin/python -m scripts.deploy_guarded` from
`~/prompta`. This is the standard release path; avoid direct `git pull` plus
`systemctl restart` for application services. The command fetches GitHub main,
creates a private deployment pause marker, waits for browser-operation locks and
all durable in-flight capture/reply/delivery leases to drain, then fast-forwards,
migrates, restarts only scheduler/UI/delivery/manual workers, verifies health,
and releases the queue. The persistent browser service and tabs are untouched.

Scheduler and UI enqueue work durably while paused. The delivery worker, manual
reply worker and read-only historical recovery all honour the same marker; an
admitted browser operation holds a shared flock for its lifetime. The deploy
creates the marker before waiting for the exclusive flock, closing the race
between the final idle check and a new send. Existing passive captures may run
past the initial delivery call, so the deployment also checks their SQLite
capture leases. If draining exceeds 60 minutes or the stores cannot be verified,
the deployment defers without changing services and removes its own pause.
After a failed update the pause stays in place; investigate before using
`python -m scripts.deploy_guarded --resume`. Worker systemd shutdown allowances
are unbounded so an operator-initiated stop does not forcibly kill a capture.
For the **first** rollout of the gate, stop legacy workers gracefully before
updating checkout code: they cannot honor a marker until restarted on this
version.

## HTTP API

`prompta-ui` serves a FastAPI application through Uvicorn on `127.0.0.1:8765`.
Strict Pydantic models validate JSON requests, discriminated job actions, query
parameters, and configuration sections. The API keeps its existing JSON error
contract and uses HTTP 400 for invalid input, 409 for conflicts, and 405 for
unsupported methods. OpenAPI is available at `/openapi.json` and `/docs`.

Synchronous storage and browser recovery calls run in FastAPI's thread pool.
The application lifespan maintains the UI heartbeat, systemd watchdog, and
orphan recovery independently of requests. Uvicorn access logging is disabled;
unexpected HTTP failures are contained and logged only by exception type.
Validation errors never return input values. Request bodies are bounded while
streaming, including chunked uploads.

## Runs and replies

The scheduler queues due jobs. The delivery worker opens a fresh ChatGPT tab, confirms prompt acceptance, and captures the final response from that tab's conversation POST or semantic DOM changes. Captures run independently and require explicit completion evidence. Verified response changes refresh the tab's activity clock; the watchdog reaps owned tabs after 45 minutes of inactivity.

Clicking Send durably queues a reply to the stored conversation and parent. The worker verifies the exact branch, recovering its latest parent when needed. Failed verification preserves the draft for another attempt or an explicit **Continue in new chat** action. A Send on a run lacking a conversation ID creates a fresh chat with its saved transcript and available original images.

Each idempotency key identifies one immutable payload. Uncertain local receipts retain that key. Ambiguous ChatGPT submissions end in `outcome_unknown` for user review. Prepared reply intents remain local until explicit dispatch.

## Storage and updates

Private SQLAlchemy SQLite WAL stores hold queue state, per-send prompts, final assistant text, bounded/redacted tool summaries, completion status, and branch identity. Image bytes use private hashed files with SQLite metadata. State lives under `~/.local/state/prompta/`; directories use mode 0700 and database/WAL files use 0600. Logs contain operational metadata. Tool details appear in the owner-local transcript.

Chats listing, search, and refresh read local storage. A shared `/api/events` EventSource, served by `sse-starlette`, sends `sync`, `jobs`, and `chats` invalidations; local GET endpoints provide the data. The library manages event encoding, HTTP transport, disconnect cancellation, 15-second heartbeats, and a 30-second send timeout. The client uses automatic reconnection and a 60-second visible-tab fallback refresh. Stable React component and list identities preserve navigation, drafts, and scroll state.

Each SQLite schema family has an independent Alembic revision table: runtime
(jobs, scheduler state, delivery queue, health), results (transcripts, replies,
local read/pin receipts, historical recovery), and ownership (tab activity).
Versioned baseline revisions adopt existing unversioned tables. Follow-up
revisions add legacy columns and transfer the old account read gate without
overwriting a newer gate. Schema upgrades run under `BEGIN IMMEDIATE` across
processes and a process lock around Alembic's context. DDL and revision markers
commit together; an unknown revision fails startup. Stores apply pending
revisions on initialization, and `prompta-migrate` upgrades all default stores
before service restart. Schema definitions in revisions are frozen and never
import mutable application metadata.

## Response recovery

Live recovery reads the installed observer in the same owned tab every 45 seconds within its activity lease. Historical recovery selects interrupted or unavailable local runs with a verified conversation UUID and an expired capture lease. It opens that exact conversation in a temporary read-only tab, verifies the route and original prompt, and captures visible assistant output. Completion requires a rendered Copy action with generation finished. Completed records stay immutable.

Historical navigation is globally paced to 90 seconds. Per-chat retry delays grow from 90 seconds to one hour. HTTP 429 responses trigger persisted read backoff starting at five minutes, doubling to a 30-minute cap with jitter and support for longer `Retry-After` values. Security challenges pause reads for 30 minutes. Delivery admission and read backoff use separate gates.
