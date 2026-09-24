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
