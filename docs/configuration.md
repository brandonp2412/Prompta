# Configuration

Settings live in `~/.config/prompta/config.toml`.

## Working hours

```toml
[working_hours]
enabled = true
start = "22:30"
end = "08:00"
timezone = "Pacific/Auckland"
```

Scheduled deliveries wait for this window. The start is inclusive; the end is exclusive. Overnight windows work across midnight. Explicit `once` and **Fire now** actions run immediately, subject to account backoff and resource availability. Delivery runs at any time by default.

## Parallelism

```toml
[parallelism]
max_workers = 3
```

This positive integer caps pending scheduled deliveries and active captures. The default is unlimited. Waiting jobs stay due, and active jobs finish under their existing leases. Manual sends have separate admission. Changes apply while the scheduler runs.

For a group of jobs with different daytime and overnight limits:

```toml
[stage_concurrency]
enabled = true
job_prefixes = ["prompta-chat-ui-", "prompta-mobile-ux-v2-"]
timezone = "Pacific/Auckland"
night_start = "22:30"
night_end = "07:00"
day_limit = 1
night_limit = 3
```

This optional policy counts pending deliveries and active captures for matching job prefixes. Per-job mutex groups also apply. Invalid enabled settings pause admission for the group.

## Connector approvals

```toml
[connector_approval]
enabled = true
```

This authorizes connector permission grants **only during an active Prompta-owned fresh-chat capture or explicit user-started exact-branch reply capture**. The owned-tab supervisor checks the live connection throughout its lifetime; it never scans the ChatGPT sidebar or other chats. The handler prefers **Always allow**, but can use **Allow once** if persistent approval is unavailable or repeatedly ignored. It retries delayed controls with bounded backoff and uses a real browser click when a synthetic click has no effect. It acts only on recognizable permission groups, not unrelated buttons.

After changing the setting, restart the affected delivery/manual-reply workers once active captures have finished. Live Prompta-owned capture tabs check every 200 ms; no independent approval watcher or account-wide approval scanning exists.
