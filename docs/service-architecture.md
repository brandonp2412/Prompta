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

From Glass, run `python -m scripts.deploy_release` after pushing `main`. It archives
committed UI/backend source, builds the UI through `buildq`, and uploads the combined
release to Nox. It invokes `scripts.deploy_guarded` using the uploaded code, so even
the deployment logic belongs to the new release. The Nox deployer installs a release
Python environment through `buildq` before interrupting service.

The deployer pauses admissions, records active sends and replies in
`deployment-interrupted.json`, and immediately stops and kills all application workers.
The persistent browser service stays running. Only after every old owner stops does
it migrate databases and transfer the recorded captures to recovery with their active
statuses and parallelism slots intact. Recovery uses exact stored conversations and
branches; it never resends a prompt.

New delivery and reply workers start behind the pause and publish readiness with their
actual PIDs. The UI and scheduler restart on the same release. Health and durable-work
checks must pass before admissions and recovery resume. A recovering chat retains its
slot for the existing 15-minute idle window. A clean read of the exact conversation and branch refreshes the existing idle
window, as does verified generation or changed response text, tools, or display blocks.
Failed or unverified reads do not refresh it. Completion releases the slot immediately. Idle expiry marks recovery
interrupted and allows queued work to advance, while later history recovery remains
possible.

`worker-generation.json` records the serving workers and `worker-handover.json` the
replaced workers and revision. Failures after shutdown begins leave admissions paused.
Use `python -m scripts.deploy_guarded --resume` only after checking service health.
Workers run from immutable releases. The checkout sync timer advances `~/prompta`
only after original checkout owners stop, and host overrides carry into new workers.

Browser-crash recovery remains a separate emergency operation that inventories
and interrupts all worker generations before restarting a crashed browser.

## Browser watchdog

`prompta-browser-watchdog.timer` checks every 20 seconds. While browser operations
are idle, it verifies both the CDP endpoint and a fresh blank renderer executing
JavaScript. Two consecutive failures restart the configured browser service;
restarts have a five-minute cooldown and intentionally stopped services stay
stopped. A nonblocking exclusive deployment lock prevents probes and restarts
from racing worker operations; active durable send/capture leases also defer
recovery. Deployment pauses skip watchdog checks.

On Nox, the watchdog's `PROMPTA_CHROME_DEBUGGER_ADDRESS` and
`PROMPTA_BROWSER_SERVICE` must match the delivery worker's browser (currently
`127.0.0.1:9222` and `prompta-browser.service`). A stale FlareSolverr override
must not redirect checks to its separate browser. Install the checked-in
`systemd/nox/prompta-browser-watchdog.service.d/90-delivery-browser.conf` under
`~/.config/systemd/user/prompta-browser-watchdog.service.d/`, run
`systemctl --user daemon-reload`, and enable the watchdog timer.

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

Live recovery reads the installed observer in the same owned tab every 45 seconds within its activity lease. Historical recovery selects interrupted or unavailable local runs and active deployment recovery captures with a verified conversation UUID and no live capture owner. It opens that exact conversation in a temporary tab, verifies the route and original prompt, and captures visible assistant output. Explicit manual requests, deployment-interrupted captures, and surviving owned tabs can resume connector permissions when automatic approval is configured; approval rechecks the exact turn and branch before acting. Recovery never resends a prompt. Completion requires a rendered Copy action with generation finished. If ChatGPT continues the response under a new message ID, the verified turn must contain the saved message ID before recovery can replace it. Completed records stay immutable.

Historical navigation is globally paced to 90 seconds. Attempt counts provide fair scheduling without a separate per-chat cooldown. HTTP 429 responses trigger persisted read backoff starting at five minutes, doubling to a 30-minute cap with jitter and support for longer `Retry-After` values. Security challenges pause reads for 30 minutes. Delivery admission and read backoff use separate gates. Logs record manual requests, selected turns, permission outcomes, observed and stored text lengths, and completion without logging response bodies.
