# Prompta

Prompta schedules one-off and recurring prompts for ChatGPT. Each run opens a fresh chat and passively captures the assistant's response from its owned tab. The mobile-friendly web UI manages jobs and shows local read-only results, without accessing account-wide ChatGPT history.

<p align="center">
  <img src="docs/prompta-cli.png" alt="Prompta CLI" width="900">
</p>

<p align="center">
  <img src="docs/prompta-ui-mobile.png" alt="Prompta web UI on mobile" width="360">
</p>

## Run

```bash
git clone https://github.com/brandonp2412/Prompta.git ~/prompta
cd ~/prompta
uv sync --locked
bun install --frozen-lockfile
bun run build

mkdir -p ~/.config/systemd/user
cp systemd/prompta-*.service systemd/prompta-*.timer systemd/prompta.target ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now prompta.target prompta-browser-watchdog.timer
```

The Jobs and Chats UI is at `http://127.0.0.1:8765`. Its Chats view reads only Prompta's private local SQLite results. Explicit Send clicks durably enqueue their exact-branch replies to `prompta-manual-reply-worker.service`, so redeploying the UI does not terminate an accepted reply capture. Prepared-only intents cannot be sent by this worker, and ambiguous sends are never retried automatically. The CLI is available as `uv run prompta`, for example:

```bash
uv run prompta add nightly-review "Review the project and improve it" --daily-at 21:00
uv run prompta edit nightly-review "Review the project, improve it, and update the ledger"
uv run prompta list
uv run prompta once "Run this immediately in a fresh chat"  # unpinned by default
uv run prompta once --pin "Run this and pin the new chat"
uv run prompta at 21:30 one-shot "Run once at 9:30pm" --pin
uv run prompta once --job nightly-review  # fire an existing job and restart its interval
```

## Working hours

To prevent Prompta from starting ChatGPT delivery work outside a local-time window, create
`~/.config/prompta/config.toml`:

```toml
[working_hours]
enabled = true
start = "22:30"
end = "08:00"
timezone = "Pacific/Auckland"
```

The start time is inclusive and the end time is exclusive. Overnight windows are supported.
Scheduled jobs remain durable while delivery is blocked and resume when the window opens.
Explicit `once` and UI **Fire now** sends bypass the working-hours window, but still obey
account backoff, resource constraints, and the global send gap. Firing an interval job
restarts its countdown from the manual trigger time, replacing any pending scheduled
send that has not started. Already-running sends cannot be interrupted. Fixed-time
daily and one-time schedules are unchanged. An ad-hoc `once` prompt has no schedule
to reset. If
`working_hours` is omitted or disabled, Prompta can deliver at any time.


## Global parallelism

Scheduled Prompta jobs have **unlimited parallelism by default**. To cap all
automatic jobs to three ongoing workers, add this to
`~/.config/prompta/config.toml`:

```toml
[parallelism]
max_workers = 3
```

The cap covers pending scheduled deliveries and live response captures, even
when a one-shot job is removed from the job list. Jobs waiting for a free slot
stay due; running jobs are never interrupted when the cap is lowered. Changes
are loaded without restarting the scheduler. Remove `max_workers` (or the
whole section) for unlimited parallelism. The value must be a positive integer.
Explicit manual sends are not blocked by this automatic-job admission cap.
Per-job mutex groups and the optional stage-specific concurrency policy still
apply.


## Optional stage concurrency

Prompta has **no time-of-day parallelism limit by default**. To opt in for specific
jobs, add this to `~/.config/prompta/config.toml` (alongside any existing sections):

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

This limits the named group to one ongoing job during the day and up to three at
night. Admission counts pending fresh-chat deliveries and active per-job passive
captures, including one-shot jobs already removed from the schedule. It does not
interrupt an accepted job when the cap falls at 07:00. Changes to this configuration
are picked up without a scheduler restart. Omitting the section or setting
`enabled = false` disables this special parallelism cap; explicitly configured
per-job mutex groups continue to enforce their ordinary serialization rules.
Invalid enabled settings fail closed rather than silently lifting the limit.


## Login to ChatGPT

Prompta uses a dedicated Chromium profile. Stop the background browser, open that same profile visibly, and log in at ChatGPT:

```bash
systemctl --user stop prompta-browser.service

/opt/brave-bin/brave \
  --user-data-dir="$HOME/.local/state/prompta/chrome-profile" \
  --profile-directory=Default \
  --password-store=basic \
  --remote-debugging-port=9222 \
  https://chatgpt.com
```

After login, close that browser window and start Prompta's browser again:

```bash
systemctl --user start prompta-browser.service
```

## Connector permissions

Passive response capture retains each Prompta-owned tab only until completion, interruption, or the existing hard 45-minute TTL. To automatically select “Always allow” on successive permission dialogs within that bound, add to `~/.config/prompta/config.toml`:

```toml
[connector_approval]
enabled = true
```

Restart `prompta-delivery-worker` and `prompta-connector-approval-watch` after changing this setting. Delivery is acknowledged immediately; approval handling and passive response capture run independently. The live capture/reply watcher uses the same approval supervisor and checks its owned chat every 200 ms. The separate backup watcher stays alive across deliveries, inspects only unread indicators in the rendered ChatGPT sidebar, and opens those chats in background tabs to grant successive permission dialogs for at most 45 minutes per chat (checking each once per second). It also checks permission controls in already-open non-Prompta ChatGPT tabs, so another request is not missed after a conversation has been marked read; it does not navigate or close those tabs. It never reads conversation text, calls a history API, or sends messages. All background navigations and sidebar refreshes obey the same durable account-wide ChatGPT read-rate-limit backoff as historical recovery; observed HTTP 429s update that shared gate. A failed or unhydrated conversation is not considered an inspected approval, and can be retried after cooldown. Locally inspecting permission controls in an already-loaded tab does not make network read requests. Automatically granting **Always allow** authorizes the requested connector permissions; only enable this for an account where you intend that behaviour.
