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

On Nox, run `./.venv/bin/python -m scripts.deploy_guarded` from `~/prompta`.
Each deployment archives the fetched main revision into a unique directory under
`~/.local/state/prompta/releases/` and installs its own Python environment through
`buildq`. Workers execute modules from that fixed directory, so later checkout
and dependency changes cannot change the code of a running capture.

The deployer briefly pauses new admissions, initializes the new delivery and
manual reply workers, and verifies readiness against their actual PIDs. It then
queues graceful retirement of the previous pair. Retiring workers accept no new
work and finish their existing sends and captures without a deadline. Their
browser transport children stay alive: systemd signals only the main process
(`KillMode=mixed`, `SendSIGKILL=no`, `TimeoutStopSec=infinity`). Persistent retirement
conditions prevent an old target dependency from resurrecting retired workers.
Only the newest pair is enabled for startup. Multiple older generations may drain
at once.

The UI and scheduler restart on the new release and admissions resume after
health verification. The browser service is untouched. Capture leases are never
expired by routine deployment. `worker-generation.json` records the serving
workers, and `worker-handover.json` records the retiring workers and deployed
revision. Failures before retirement leave the original workers serving; failures
after retirement retain the admission pause for operator recovery using
`python -m scripts.deploy_guarded --resume` after checking service health.

During the first rollout, the original workers still load from `~/prompta`.
Only the deployment scripts may be upgraded there before their retirement; loaded
application source remains pinned until they finish. A persistent checkout sync
timer advances the checkout after both original workers exit. Subsequent workers
all use release snapshots. Host overrides, including browser endpoints and watchdog
budgets, carry into each new generation. Schema revision changes are rejected
before handover because old workers cannot recognize a new migration head.
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

Live recovery reads the installed observer in the same owned tab every 45 seconds within its activity lease. Historical recovery selects interrupted or unavailable local runs with a verified conversation UUID and an expired capture lease. It opens that exact conversation in a temporary tab, verifies the route and original prompt, and captures visible assistant output. Explicit manual requests, deployment-interrupted captures, and surviving owned tabs can resume connector permissions when automatic approval is configured; approval rechecks the exact turn and branch before acting. Recovery never resends a prompt. Completion requires a rendered Copy action with generation finished. If ChatGPT continues the response under a new message ID, the verified turn must contain the saved message ID before recovery can replace it. Completed records stay immutable.

Historical navigation is globally paced to 90 seconds. Attempt counts provide fair scheduling without a separate per-chat cooldown. HTTP 429 responses trigger persisted read backoff starting at five minutes, doubling to a 30-minute cap with jitter and support for longer `Retry-After` values. Security challenges pause reads for 30 minutes. Delivery admission and read backoff use separate gates. Logs record manual requests, selected turns, permission outcomes, observed and stored text lengths, and completion without logging response bodies.
