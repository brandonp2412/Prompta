# Passive response capture — Stage 3 handoff (2026-10-27)

- `GET /api/results?limit=20&offset=0&q=&status=` lists only SQLite `job_responses` rows created by Prompta sends. It returns bounded previews and total count. `GET /api/results/{send_id}` returns only a single run's user prompt, assistant output, source, state, and times. No ChatGPT calls, browser opening, or GET/history integration. Both routes are read-only and `no-store`; result request paths and search terms are excluded from server logs.
- `ChatsPage.svelte` adds a mobile-first Jobs/Chats navigation, per-date run list, search/filter, pagination, status labels, NZ-local 12-hour times, and a read-only detail with partial/unavailable handling. `ResultMarkdown.svelte` renders safe tokenized Markdown/code; raw HTML is displayed as text, remote images are never fetched, and links permit only HTTP(S). UI refresh reads SQLite only (15-second visible-tab interval).
- Stage 1/2 safeguards are unchanged: unique run leases, no re-sends or replies, fresh tabs, original owned-tab 45-minute TTL, approvals, durable global rate-limit backoff, no history polling and no Machine Gun. AGENTS.md already contains the narrow read-only authorization.
- Tests: full Ruff, Ty, Python pytest, Bun TypeScript helper tests, Svelte strict checking, production build, and local Playwright desktop/mobile screenshots using **synthetic** run data. UI browser-request assertions checked that repeated refreshes did not contact ChatGPT. Do not save real responses in screenshot/build artifacts.

## Stage 4

1. Deploy on Nox after serializing `main` integration under `/home/brandon/prompta/.git/prompta-main-merge.lock`. Reinstall strict editable package with `uv sync --locked --reinstall-package prompta`; verify imports before restarting. Confirm scheduler, delivery worker, UI, and watchdog health.
2. Open Nox UI on desktop and Samsung/mobile browser; verify actual local stored runs, status transitions, pagination, Markdown/code, back navigation, 12-hour timestamps, and that refresh emits **zero** ChatGPT requests. Never reopen a historical tab or backfill.
3. Only if authorized, run one controlled fresh-chat canary through the normal scheduler, observe eventual completed/partial/unavailable state, and verify cleanup/backoff/TTL. Do not add requests for reading, replies, notifications, or account history.
