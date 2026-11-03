# Configuration

Settings live in `~/.config/prompta/config.toml`.

## Concurrency

```toml
[concurrency]
enabled = true
max_workers = 3
```

When enabled, this is the **single global limit** on simultaneous fresh-chat
deliveries and owned captures, regardless of whether they came from `once`,
a one-time scheduled job, a recurring job, **Fire now**, or a new chat in the UI.
Every eligible due job is durably queued; excess work waits for an available slot.
Existing per-job mutex groups still apply. Jobs are admitted in queue order,
with manually requested chats prioritized.
Explicit replies do not consume fresh-chat slots.

Omitting `[concurrency]` disables the cap (unlimited concurrency). A present
`[concurrency]` table defaults to enabled for compatibility with existing
`max_workers`-only files. Legacy `[parallelism]` is read if `[concurrency]` is
absent; the UI saves only `[concurrency]` and removes the old section. The positive `max_workers` value is required when enabled. Lowering it does not interrupt already active
captures; it blocks new claims until occupancy drops below the limit. The
scheduler and worker read changes without restarting.

There are no time windows, timezone rules, or job-prefix filters. If different
limits are wanted at different times, use your own cron jobs to update the
configuration.

## Conversation recovery

Background network recovery checks explicit recovery requests and chats interrupted
by deployment. Older incomplete chats, including pinned chats, require the Chats
recovery action; pinning alone does not schedule network reads. Recovery never
resends the original prompt. Capture from already-open owned tabs continues.

All recovery workers and generations share one durable five-minute recovery slot.
A read HTTP 429 pauses network recovery, with exponential delays from five minutes
up to two hours, plus jitter. Longer server retry instructions take precedence.
Escalation survives restarts and expires after 24 hours without another 429, or
clears after a successful network recovery once the cooldown has elapsed. Only one
worker can acquire the next recovery slot when a cooldown expires. Fresh-chat
concurrency and read cooldowns are separate; a read cooldown does not block sends.

## Connector approvals

```toml
[connector_approval]
enabled = true
```

This authorizes connector permission grants **only during an active Prompta-owned fresh-chat capture or explicit user-started exact-branch reply capture**. The owned-tab supervisor checks the live connection throughout its lifetime; it never scans the ChatGPT sidebar or other chats. The handler prefers **Always allow**, but can use **Allow once** if persistent approval is unavailable or repeatedly ignored. It retries delayed controls with bounded backoff and uses a real browser click when a synthetic click has no effect. It acts only on recognizable permission groups, not unrelated buttons.

After changing the setting, restart the affected delivery/manual-reply workers once active captures have finished. Live Prompta-owned capture tabs check every 200 ms; no independent approval watcher or account-wide approval scanning exists.
