# Prompta

Prompta is the only fork-specific feature in this repository. It opens a brand-new ChatGPT conversation for each configured job on its own cadence, verifies High thinking effort, sends the prompt, confirms the send, and applies persisted exponential backoff when ChatGPT rate-limits it.

It does not inspect existing chats and does not re-prompt unfinished conversations.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run ty check
```

## Jobs

Jobs default to every 30 minutes:

```bash
uv run prompta add flux-roadmap "Continue work on the flux roadmap on glass. Do the maximum amount of work possible. Report percent progress complete at the end"
uv run prompta list
uv run prompta show flux-roadmap
uv run prompta remove flux-roadmap
```

Runtime data defaults to:

- `~/.config/prompta/jobs.json`
- `~/.local/state/prompta/state.json`
- `~/.local/state/prompta/firefox-profile`

The Firefox profile must already be logged in to ChatGPT.

## Upstream maintenance

The repository root intentionally stays on the original `Octo-Lex/ChatGPT-Web2API` tree. Prompta lives entirely under this directory, plus its additive GitHub Actions workflow. That keeps upstream updates low-conflict:

```bash
git fetch upstream
git merge upstream/master
```

A rebase onto `upstream/master` is also straightforward because Prompta does not modify upstream Python modules.
