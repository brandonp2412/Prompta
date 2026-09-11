# Prompta

Prompta opens a brand-new ChatGPT conversation for each configured job on its own cadence. It verifies High thinking effort, sends the prompt, confirms the send, and persists exponential backoff when ChatGPT rate-limits it.

Rate limits pause the entire scheduler rather than only the job that encountered them. The account-wide cooldown survives service restarts, ordinary browser/send failures retain their retry cooldown across restarts, and send attempts are spaced by at least five minutes. New jobs get a persisted random initial delay, while successful recurring jobs add up to five minutes of jitter to their normal cadence so equal-interval jobs do not keep bunching together.

Observed rate-limit responses on the current High-effort workload have imposed roughly five-minute cooldowns after clustered sends. Prompta therefore starts account-wide exponential backoff at five minutes and escalates repeated limits to 10, 20, then 30 minutes, with a small random jitter.

It does not inspect existing chats and does not re-prompt unfinished conversations.

## Setup

```bash
uv sync --locked
```

The Firefox profile used by the service lives at `~/.local/state/prompta/firefox-profile` and must be logged in to ChatGPT.

## Manage jobs

Jobs default to every 30 minutes:

`list` and `show` display each prompt's status and next due time. Status icons are `●` healthy, `✗` failing, and `○` pending.

```bash
# List jobs
uv run prompta list

# Show one prompt
uv run prompta show flux-roadmap

# Add or replace a 30-minute job
uv run prompta add my-job "Do the maximum amount of work possible."

# Add or replace a job with another cadence
uv run prompta add my-job "Do the maximum amount of work possible." --interval-minutes 60

# Add or replace a job at an exact local clock time every day
uv run prompta add daily-check "Check the thing." --daily-at 07:00

# Remove one job
uv run prompta remove my-job

# Remove all jobs
uv run prompta clear
```

Runtime data defaults to:

- `~/.config/prompta/jobs.json`
- `~/.local/state/prompta/state.json`
- `~/.local/state/prompta/firefox-profile`

## Service

```bash
systemctl --user status prompta
systemctl --user restart prompta
systemctl --user stop prompta
systemctl --user start prompta
journalctl --user -u prompta -f
```

The unit file is `systemd/prompta.service`.

## Development

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run ty check
```

## Upstream

Prompta was extracted from the `Octo-Lex/ChatGPT-Web2API` fork history, but is now a standalone project. The original repository is kept as the `upstream` Git remote so useful future fixes can still be imported without carrying the old application tree.

```bash
# Configure once on a fresh clone
git remote add upstream git@github.com:Octo-Lex/ChatGPT-Web2API.git

# See new upstream commits
git fetch upstream
git log --oneline HEAD..upstream/master

# Import a relevant upstream commit
git cherry-pick <commit>
```

Selective cherry-picks are preferred over merging all of `upstream/master`, because Prompta intentionally no longer contains the rest of ChatGPT-Web2API.
