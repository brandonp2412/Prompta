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

This authorizes automatic **Always allow** clicks for connector permission requests. Enable it for an account where you intend to grant those permissions.

Restart `prompta-delivery-worker` and `prompta-connector-approval-watch` after changing the setting, allowing active captures to finish first. Live owned tabs check every 200 ms. The independent watcher checks unread sidebar links in temporary background tabs and permission controls in existing non-Prompta tabs, once per second per tab. Temporary approval tabs have a 45-minute lifetime. Watcher navigation and refresh obey the persisted account read backoff.
