# Prompta split-service architecture

Prompta is deployed on Nox as five independently restartable user services under
`prompta.target`. Cross-process coordination is durable SQLite state; services must
not communicate by process-local asyncio/thread queues.

| Service | Owns | Must not own |
| --- | --- | --- |
| `prompta-ui.service` | HTTP, SSE, local UI state, durable send/schedule writes, health views | browser automation, delivery consumer thread, scheduler loop |
| `prompta-scheduler.service` | schedule evaluation and idempotent delivery enqueue | browser automation or delivery |
| `prompta-delivery-worker.service` | delivery leases, ChatGPT send interaction, retries, account backoff | schedule evaluation or conversation polling |
| `prompta-conversation-worker.service` | active-chat recovery/polling, transcript enrichment, final cache writes | send queue consumption or scheduling |
| `prompta-browser.service` | dedicated Brave process and profile | Prompta application logic |

## Functional core and imperative shells

The refactor keeps policy deterministic without turning resource ownership into value plumbing.
The main functional-core modules are:

- `snapshot_reconciliation.py`: snapshot coverage, message normalization, stable-key/handoff
  selection, and snapshot message status.
- `conversation_reconciliation.py`: completion assessment, poll-state transitions, and
  transient/delivery/final-text recovery escalation.
- `delivery_state.py`: queue eligibility, lease/completion decisions, coalescing, retry
  backoff, failure transitions, and attachment-retention policy.
- `scheduler_policy.py`: due-time/idempotency decisions, jitter bounds, retry timing, and
  scheduler state updates.
- `web_decisions.py`: HTTP query/validation/schedule/pin/send request interpretation.
- The smaller policy functions in `rate_limit.py`, `resource_pressure.py`,
  `service_health.py`, and `control_server.py` cover legacy standalone-core decisions.

Time, random jitter, persisted state, and browser observations are passed into these functions
as data. The functions return decisions or state-update values; they do not own sockets,
SQLite connections, threads, browser contexts, or systemd lifecycles.

Resource-owning classes remain imperative shells by design. `ChatCache`,
`DeliveryQueueStore`, `SchedulerRuntime`, `SendJobRegistry`, `ConversationTracker`,
`PlaywrightDriver`/browser session objects, and the HTTP/server classes keep connection,
lease, transaction, browser, and lifecycle ownership. Some shell methods remain long because
they sequence transactions or external effects; size alone is not a reason to turn those
resources into stateless adapters. New policy branches inside those shells should normally
be extracted into the functional-core modules above once they can be expressed from explicit
inputs.

`SchedulerExecution` and the standalone control socket are compatibility paths for direct CLI
operation; the deployed split stack does not use them for cross-service coordination.
`DurableSchedulerProducer.migrate_legacy_pending_intents()` is intentionally retained as a
one-way compatibility migration for pre-split queued scheduler intents, not as a second
delivery architecture.

Prompta intentionally keeps setuptools strict editable mode so static analysis resolves the
package-to-`src/` mapping exactly. Strict editable installs snapshot the module set, so a Git
update that adds or removes Python modules must be followed by
`uv sync --locked --reinstall-package prompta` before tests or Python-service restarts. Ordinary
`uv sync --locked` is not sufficient for that case because unchanged project metadata can leave
the existing editable link tree in place.

The delivery queue is `~/.local/state/prompta/ui-send-jobs.sqlite3`. Runtime,
scheduler, account-backoff, and service-health state are SQLite-backed under the
Prompta state directory. A successful delivery receipt is terminal and idempotent;
an expired `running` lease can be reclaimed after a worker crash. This prevents
duplicates when the success receipt was committed. A process killed after ChatGPT
accepted a send but before the receipt commit remains an unavoidable best-effort
window, so delivery code rechecks its lease immediately before external send and
preserves stable send/client IDs across retries.

## Recovery runbook

Inspect the stack with:

```bash
systemctl --user status prompta.target
systemctl --user status prompta-ui prompta-scheduler prompta-delivery-worker \
  prompta-conversation-worker prompta-browser
curl -fsS http://127.0.0.1:8765/api/health
```

The health payload reports each component independently. A stale worker heartbeat
does not imply the UI is dead, and a browser outage is reported separately from the
scheduler and UI.

Restart only the owner of the failed responsibility:

```bash
systemctl --user restart prompta-ui
systemctl --user restart prompta-scheduler
systemctl --user restart prompta-delivery-worker
systemctl --user restart prompta-conversation-worker
systemctl --user restart prompta-browser
```

Expected recovery behavior:

- UI restart: queued deliveries and active worker state survive in SQLite.
- Scheduler restart: an already-enqueued occurrence keeps the same idempotency key;
  it is not enqueued twice.
- Delivery-worker kill: a live lease blocks another worker until expiry, then the
  same send can be reclaimed.
- Conversation-worker restart: active-chat/cache state and poll activity are
  recoverable from SQLite; the UI stays available.
- Browser restart/hang: browser health becomes unavailable/stale while scheduler and
  UI health remain independently visible; browser-owning workers retry after recovery.
- Account rate limit: account-wide backoff is persisted and blocks delivery after a
  worker restart until the backoff expires.
- Resource pressure: delivery admission is blocked without consuming queue work and
  resumes when the persisted admission condition clears.
- Repeated restart after committed send success: the terminal receipt is not
  claimable and idempotent enqueue returns the existing receipt.

`prompta.service` is obsolete. Remove stale installed copies and keep it disabled.
The legacy standalone `prompta run` control socket exists only for direct CLI
compatibility and is not part of the deployed split-service coordination path.
UI/scheduler/delivery service communication must not be moved back onto it.
