# Development

Work in the current checkout. Follow [AGENTS.md](AGENTS.md) for browser access, capture ownership, privacy, and release requirements.

## Checks

Run heavy project commands through the shared Pueue queue:

```bash
buildq --wait -- uv run --no-sync ruff check .
buildq --wait -- uv run --no-sync ty check
buildq --wait -- uv run --no-sync pytest -q
buildq --wait -- bun run check
```

Python uses strict Ruff and Ty checks. The UI uses Svelte 5, strict TypeScript, and Vite. Fix types and behavior at the source.

Svelte components own markup and view state. Use stable keyed lists and preserve component identity during navigation and refresh. Render Markdown through structured tokens. Keep browser effects in typed helpers. `bun run lint:dom` and the browser continuity tests check these boundaries.

## Release

Commit validated changes. Acquire `/home/brandon/prompta/.git/prompta-main-merge.lock` with `flock` before updating against `main`, integrating, or pushing. Hold it through the push, then deploy `main` to Nox.

On Nox, update `/home/brandon/prompta`. Adding Python modules requires `buildq --wait -- uv sync --locked --reinstall-package prompta` to refresh strict editable imports. Verify imports before restarting affected services. Allow active delivery and reply captures to finish; the manual-reply worker drains captures on shutdown. Check service health and `GET /api/health` after deployment. Documentation changes take effect when the checkout updates.

For a deliberate live delivery/capture check that creates a real ChatGPT chat:

```bash
.venv/bin/python scripts/run_chatgpt_e2e.py --verify-capture --timeout-seconds 240 --capture-timeout-seconds 360
```
