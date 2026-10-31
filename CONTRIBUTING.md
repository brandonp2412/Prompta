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

Python uses strict Ruff and Ty checks. The UI uses React 19, strict TypeScript, signal-backed controllers, and Vite. Fix types and behavior at the source.

React components own markup; signal-backed controllers preserve view state. Use stable keyed lists and preserve component identity during navigation and refresh. Render Markdown through structured tokens. Keep browser effects in typed helpers. `bun run lint:dom` and the browser continuity tests check these boundaries.

## API and schema changes

The API factory is `prompta.web:create_app`; `prompta-ui` runs it with Uvicorn.
Use strict Pydantic request models and keep browser/dispatch policy in services.
The real HTTP/browser tests use Uvicorn; framework boundary tests use FastAPI's
TestClient. Set `PROMPTA_TEST_CHROMIUM` to your Chromium/Brave executable when it
is not installed at `/usr/bin/chromium`. On Glass, use
`PROMPTA_TEST_CHROMIUM=/opt/brave-bin/brave`: the `~/.local/bin/chromium` wrapper
may exist even when its `/usr/bin/chromium` target does not. Browser-launch
failures must not be mistaken for application regressions or passing skips.

Create a revision in the affected family rather than adding schema inspection
or `ALTER TABLE` to a store constructor:

```bash
buildq --wait -- uv run alembic --name runtime revision -m "Describe the schema change"
# Use --name results or --name ownership for those databases.
buildq --wait -- uv run prompta-migrate --state-dir /path/to/private/test-state
buildq --wait -- uv run prompta-migrate --database /path/to/custom.sqlite3 --family runtime
```

Keep revisions independent of application table definitions. Test a fresh
installation and a populated older schema, including rollback after failure.
The one-time baseline adoption checks belong in the existing baseline/legacy
revisions; subsequent migrations should target the known preceding revision.
The migration environment requires a caller-owned serialized connection; use
`prompta-migrate` to apply upgrades. Inspect history with
`uv run alembic --name runtime history`.

## Release

Commit validated changes. Acquire `/home/brandon/prompta/.git/prompta-main-merge.lock` with `flock` before updating against `main`, integrating, or pushing. Hold it through the push, then deploy `main` to Nox.

On Nox, update `/home/brandon/prompta`. Adding Python modules requires `buildq --wait -- uv sync --locked --reinstall-package prompta` to refresh strict editable imports. Verify imports, take private SQLite backups, and run `buildq --wait -- .venv/bin/prompta-migrate` before restarting affected services. Allow active delivery and reply captures to finish; the manual-reply worker drains captures on shutdown. Check service health and `GET /api/health` after deployment. Documentation changes take effect when the checkout updates.

For a deliberate live delivery/capture check that creates a real ChatGPT chat:

```bash
.venv/bin/python scripts/run_chatgpt_e2e.py --verify-capture --timeout-seconds 240 --capture-timeout-seconds 360
```
