# Passive ChatGPT capture — Stage 2 handoff (2026-10-26)

- Stage 1 (`5fad648`) remains unchanged in its pure SSE parser. Stage 2 binds the
  existing POST and mutation observer to the **same newly opened, owned job tab**.
  In-page semantic DOM changes are pushed over Playwright's local page binding;
  no ChatGPT read requests, historical navigation, or periodic scraping.
- The delivery worker accepts a confirmed send immediately; one bounded daemon
  capture task keeps the tab until verified final output, disconnect, or the
  pre-existing **45-minute tab TTL**. Connector `Always allow` supervision runs
  alongside capture. Only the existing single worker dispatches new prompts;
  capture threads never send. Capacity is 96 retained tabs; if exhausted,
  a new send is safely deferred before dispatch and retried by the delivery queue.
- `~/.local/state/prompta/chat-results.sqlite3` contains per-send `send_id`,
  job name, user text, assistant text, source, single branch/message identity,
  timestamps, lease owner/deadline, and states queued/accepted/generating/
  completed/interrupted/unavailable. SQLAlchemy uses WAL; Alembic creates the
  new private table/index. Directory is 0700; DB/WAL/SHM files are 0600.
  `ResponseStore.records/get` are local-only read entry points for Stage 3 UI.
- A completed response requires an explicit finished SSE final message or
  semantic DOM completion; acceptance alone never means completed. Partial
  text survives timeout/disconnect/restart. A new worker recovers dead-owner/
  expired captures without reopening old tabs. All updates are guarded by
  atomic per-send ownership and branch identity, with terminal immutability.
- Stage 3: local read-only Svelte chat/results UI, using older `db709ee` solely
  for styling. No notification/result push or ChatGPT history. Stage 4: full
  E2E/controlled canary; **no live canary was sent in Stage 2**.

Validation: Ruff, Ty, pytest, offline DOM, Svelte/TypeScript, and build.
Nox strict-editable deployment after adding `src/response_store.py` requires
`uv sync --locked --reinstall-package prompta`; verify import before restarting
services, and verify worker/scheduler/UI health after restart.
