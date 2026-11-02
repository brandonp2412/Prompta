# Development

Work in the current checkout. Follow [AGENTS.md](AGENTS.md) for browser access, capture ownership, privacy, and release requirements.

## Checks

```bash
uv run --no-sync ruff check .
uv run --no-sync ty check
uv run --no-sync pytest -q
bun run check
bun run test
```

Python uses strict Ruff and Ty checks. The UI uses React 19, strict TypeScript, signal-backed controllers, and Vite. Fix types and behavior at the source.

UI behavior tests use React Testing Library and user-event with Happy DOM. `bun run test` runs pure utility tests separately from DOM tests so browser-global stubs cannot leak between them, then runs the browser-script and lint tests under Node. Strict TypeScript checks include the React tests.

React components own markup; signal-backed controllers preserve view state. Use stable keyed lists and preserve component identity during navigation and refresh. Render Markdown through structured tokens. Keep browser effects in typed helpers. `bun run lint:dom` and the browser continuity tests check these boundaries.

## UI hot reload

```bash
bun install --frozen-lockfile
bun run dev
```

Open <http://127.0.0.1:5173>. Vite provides React Fast Refresh and CSS hot updates
for changes in `src/ui/` and `src/static/*.css`; Ctrl+C stops both servers.
The command also starts a local FastAPI instance on port 18765. Its SQLite
databases and settings live in the ignored `.prompta-dev/` directory, separate
from normal Prompta state. No delivery or scheduler worker is started.
The development page does not register the production service worker.

If you already have an API server, set `PROMPTA_DEV_API_TARGET` to its full URL to
proxy to that server without starting a local backend. Be careful: actions in
the development UI can mutate whatever API you point it at. You may override
the local backend port with `PROMPTA_DEV_API_PORT` or its state directory with
`PROMPTA_DEV_STATE_DIR`.

## API and schema changes

The API factory is `prompta.web:create_app`; `prompta-ui` runs it with Uvicorn.
Use strict Pydantic request models and keep browser/dispatch policy in services.
The real HTTP/browser tests use Uvicorn; framework boundary tests use FastAPI's
TestClient. Set `PROMPTA_TEST_CHROMIUM` to your Chromium/Brave executable when it
is not installed at `/usr/bin/chromium`. On hosts with Brave, set
`PROMPTA_TEST_CHROMIUM` to the installed browser executable: a `chromium` wrapper
may exist even when its `/usr/bin/chromium` target does not. Browser-launch
failures must not be mistaken for application regressions or passing skips.

Create a revision in the affected family rather than adding schema inspection
or `ALTER TABLE` to a store constructor:

```bash
uv run alembic --name runtime revision -m "Describe the schema change"
# Use --name results or --name ownership for those databases.
uv run prompta-migrate --state-dir /path/to/private/test-state
uv run prompta-migrate --database /path/to/custom.sqlite3 --family runtime
```

Keep revisions independent of application table definitions. Test a fresh
installation and a populated older schema, including rollback after failure.
The one-time baseline adoption checks belong in the existing baseline/legacy
revisions; subsequent migrations should target the known preceding revision.
The migration environment requires a caller-owned serialized connection; use
`prompta-migrate` to apply upgrades. Inspect history with
`uv run alembic --name runtime history`.

## Release

Commit validated changes. Acquire the checkout's `.git/prompta-main-merge.lock` with `flock` before updating against `main`, integrating, or pushing. Hold it through the push, then deploy `main` to the configured production host.

On Nox, run `./.venv/bin/python -m scripts.deploy_guarded` from the configured checkout. It records ongoing work, pauses new admissions, stops application workers within a bounded shutdown window, fast-forwards main, migrates, restarts workers, verifies health, and resumes history recovery. It preserves the browser service. See [deployment details](docs/service-architecture.md#guarded-production-deployments). Adding Python modules requires `buildq --wait -- uv sync --locked --reinstall-package prompta` to refresh strict editable imports.

For a deliberate live delivery/capture check that creates a real ChatGPT chat:

```bash
.venv/bin/python scripts/run_chatgpt_e2e.py --verify-capture --timeout-seconds 240 --capture-timeout-seconds 360
```
