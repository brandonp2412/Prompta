# Prompta

Send ChatGPT prompts once or on a schedule.

## Setup

```bash
uv sync --locked
```

Prompta automates Chromium through Playwright. The browser profile defaults to
`~/.local/state/prompta/chrome-profile` and must have an authenticated ChatGPT
session.

### Chromium / Playwright setup

Install Chromium, then perform the first login with the dedicated Prompta profile in a visible browser:

```bash
mkdir -p ~/.local/state/prompta/chrome-profile
chromium \
  --user-data-dir="$HOME/.local/state/prompta/chrome-profile" \
  --profile-directory=Default \
  --password-store=basic \
  https://chatgpt.com/
```

After logging in, **close Chromium** so Playwright can exclusively open the persistent profile.
Test the backend without changing the service default:

```bash
uv run prompta sync <conversation-id> --browser chrome --direct-browser
```

To switch the systemd worker after that test succeeds:

```bash
systemctl --user edit prompta
```

Add:

```ini
[Service]
Environment=PROMPTA_BROWSER=chrome
```

Then run:

```bash
systemctl --user daemon-reload
systemctl --user restart prompta
```

`PROMPTA_CHROME_PROFILE` and `PROMPTA_CHROME_PATH` can override the Chromium defaults.
The equivalent CLI flags are `--chrome-profile` and `--chrome-path`. Set
`PROMPTA_CHROME_DEBUGGER_ADDRESS` or `--chrome-debugger-address` to attach Playwright
to an already-running Chromium CDP endpoint instead of launching the dedicated profile.

## One-shot tasks

Run a prompt immediately without saving it or scheduling another run:

```bash
uv run prompta once "Review the latest build and report any regressions."
```

Each one-shot starts a fresh ChatGPT chat, sends exactly once, passively caches the response to completion, then exits.

## Manage jobs

Repeating jobs default to every 40 minutes:

`list` (`ls`) and `show` display each prompt's status and next due time with a
compact, colour-aware terminal UI. Status icons are `●` healthy, `✗` failing,
`○` pending, `Ⅱ` paused, and `⏳` rate-limited.

![Sample output from `prompta ls`](docs/assets/prompta-ls.png)

The screenshot is generated from the real `prompta ls` formatter with isolated,
deterministic sample jobs:

```bash
uv run python scripts/generate_readme_screenshot.py
```

```bash
# List jobs
uv run prompta ls

# Show one prompt
uv run prompta show flux-roadmap

# Add or replace a 40-minute job
uv run prompta add my-job "Do the maximum amount of work possible."

# Add or replace a job with another cadence
uv run prompta add my-job "Do the maximum amount of work possible." --interval-minutes 60

# Disable recurrence jitter when the interval must be exact
uv run prompta add my-job "Do the maximum amount of work possible." --interval-minutes 30 --exact-interval

# Add or replace a job at an exact local clock time every day
uv run prompta add daily-check "Check the thing." --daily-at 07:00

# Remove one job
uv run prompta remove my-job

# Remove all jobs
uv run prompta clear

# Pause or resume a job
uv run prompta pause my-job
uv run prompta resume my-job
```

Runtime data defaults to SQLite-backed stores:

- `~/.local/state/prompta/runtime.sqlite3` — scheduled jobs and scheduler state
- `~/.local/state/prompta/chats.sqlite3` — conversation history and capture data
- `~/.local/state/prompta/ui-send-jobs.sqlite3` — durable UI send queue and recovery
- `~/.local/state/prompta/ui-pinned-chats.sqlite3` — shared pin state
- `~/.local/state/prompta/ui-image-previews.sqlite3` — image-preview metadata
- `~/.local/state/prompta/ui-conversation-state.sqlite3` — read/unread state
- `~/.local/state/prompta/chrome-profile` — Chromium profile data

Older JSON runtime stores are imported into their SQLite replacements once and are no
longer written after migration.

## Conversation cache

Scheduled conversations stay open in browser tabs while ChatGPT is producing the
response. Prompta reads the already-rendered message DOM and React message state through
the Chromium/Playwright browser session, then writes
changed snapshots to the SQLite cache roughly once per scheduler tick. Cache capture does
not poll ChatGPT HTTP APIs or submit additional model requests.

The database uses WAL mode so another local process can read active conversations and
completed history while the scheduler keeps writing. Once an assistant response is
stable and no longer streaming, Prompta records it as complete and retains the browser
tab briefly (currently 15 seconds) for an immediate follow-up before closing it to keep
browser memory bounded. On scheduler restart, Prompta attempts to reattach
recent live conversations instead of discarding their progress.

## Web UI

A founding principle of the Prompta UI is to minimize interaction with ChatGPT. Navigation,
presentation state, pinning, sharing, caching, search, scheduling metadata, and other work
that can be handled locally should stay local; Prompta should contact or manipulate ChatGPT
only when the requested action actually requires ChatGPT.

Prompta includes a local ChatGPT-style viewer for active runs and cached history:

![Prompta conversation UI](docs/assets/prompta-ui.png)

```bash
uv run prompta-ui
```

Open `http://127.0.0.1:8765`. The UI reads the SQLite database using
`mode=ro` plus `PRAGMA query_only=ON`. The browser reads SQLite-backed API state directly,
then an SSE stream tells the client when the SQLite cache or send state changed, so
active chats update without page polling or reload flicker. Sending a message uses the
scheduler control socket and reuses a retained live tab when one exists; an expired
historical chat is opened only for an explicit send.

The UI is installable as a PWA with a service worker and the `Prompta · Nox` manifest. While the UI/PWA is running,
browser notification permission lets an active-to-complete transition produce a
system notification. Recurring jobs can be created directly from the composer:

```text
/add 30 fix bugs
/add 30s check the latest failures
/add 2h review the latest failures
/add 1d summarize open work
```

Intervals accept seconds, minutes, hours, and days from 6 seconds through 30 days.
Repeating an equivalent command reuses the existing schedule. Use `/list` in the
composer to open the scheduled-jobs manager. Its add, edit,
pause, resume, remove, and clear actions map to the corresponding Prompta CLI
commands. `/every` and `/jobs` remain accepted as compatibility aliases.

Features also include client-first optimistic sends with SSE reconciliation, replies
to existing chats, history grouped by recency, full-text search across cached
prompts/messages, safe Markdown and code rendering, responsive mobile layout, deep
links to cached chats, and dark/light appearance following the browser preference.

Prompta runs only on Nox: the browser worker, scheduler control socket, SQLite
conversation cache, logs, and UI on port 8765 all live there. If the backend is
unavailable, the UI starts `prompta.service` and fails the send if it does not become
ready.

Install `systemd/prompta.service`, `systemd/prompta-browser.service`, and
`systemd/prompta-ui.service` under `~/.config/systemd/user/`. The browser unit uses the
dedicated Prompta profile and clears only its saved tab-session files before startup,
so Chromium cannot restore stale automation tabs after a restart. The UI unit wants the local worker but remains available across worker restarts and uses
`--preserve-active` so a UI-only restart cannot mark worker-owned live conversations
interrupted. Remove legacy `prompta-cache-sync.timer` and `prompta-cache-sync.service` when upgrading.

## Service

```bash
systemctl --user status prompta
systemctl --user restart prompta
systemctl --user stop prompta
systemctl --user start prompta
journalctl --user -u prompta -f

# Web UI
systemctl --user status prompta-ui
```

The unit files are `systemd/prompta.service`, `systemd/prompta-browser.service`, and
`systemd/prompta-ui.service`.

## Development

The browser UI uses Svelte 5 and TypeScript in src/prompta/ui/. Vite builds the
committed browser bundle at src/prompta/static/app.js, which is served by the existing
Python UI server. The legacy behavior modules are being migrated incrementally into
Svelte components so live conversation DOM nodes keep stable identity during updates.

```bash
uv sync --locked
bun install --frozen-lockfile
bun run check
uv run pytest
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run ty check
uv run python scripts/generate_readme_screenshot.py
```

## Upstream

Prompta was extracted from the `Octo-Lex/ChatGPT-Web2API` fork history, but is 
now a standalone project. The original repository is kept as the `upstream` Git 
remote so useful future fixes can still be imported without carrying the old 
application tree.

```bash
# Configure once on a fresh clone
git remote add upstream git@github.com:Octo-Lex/ChatGPT-Web2API.git

# See new upstream commits
git fetch upstream
git log --oneline HEAD..upstream/master

# Import a relevant upstream commit
git cherry-pick <commit>
```

Selective cherry-picks are preferred over merging all of `upstream/master`, 
because Prompta intentionally no longer contains the rest of ChatGPT-Web2API.
