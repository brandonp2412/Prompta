# Passive response capture — Stage 1 handoff (2026-10-26)

## Delivered

- src/response_capture.py is a bounded pure SSE parser for an already-observed conversation POST: legacy snapshots, add/append/patch, final-only text, branch identity, terminal signals, and explicit incomplete statuses. It never requests data or parses GET history.
- PlaywrightDriver binds the first POST already emitted from the new owned tab using page.on("request"/"response"), reads its body only after the response finishes, and exposes captured_assistant_response(capture). No outgoing HTTP call is added.
- src/browser_scripts/passive_response_observer.js installs before sending, baselines existing assistant nodes, and observes semantic DOM mutations coalesced at 450 ms. passive_response_read.js reads a snapshot on the same owned tab. No navigation, history, or repeated polling.
- Existing dispatcher still closes ordinary tabs immediately after acceptance; Stage 2 must extend lifetime within the established 45-minute hard TTL to retain normal completed responses. During Stage 1, extraction is opportunistic (and available on approval-retained tabs). No live canary was sent.

## Pinned source review

- [stufently conversation-read.js](https://github.com/stufently/gpt-web-gateway/blob/945182a/src/lib/conversation-read.js) and [chatgpt.js](https://github.com/stufently/gpt-web-gateway/blob/945182a/src/chatgpt.js): legacy/delta SSE conventions and passive interception. Never port its history GET and account-wide logic.
- [qayshp dom-runtime.js](https://github.com/qayshp/chatgpt-playwright-backend/blob/85b930e/src/dom-runtime.js): semantic message IDs, markdown, stop/copy, and MutationObserver patterns. No polling/history features.
- [FirstWari selectors.py](https://github.com/FirstWari/chatgpt-web/blob/86383d5/chatgpt_web/selectors.py) and [chat.py](https://github.com/FirstWari/chatgpt-web/blob/86383d5/chatgpt_web/chat.py): selector and completion hints, not its send/continue/regenerate or high-rate wait logic.
- Historical db709ee: SidebarList.svelte, ConversationMessages.svelte and MarkdownContent.svelte inspected for Stage 3 visual styling only. Do not restore its architecture.

## Exact Stage 2 checklist

1. Associate the current owned tab and first POST capture with one fresh job run. After confirmed acceptance, retain that same tab only until completed evidence, explicit error/timeout, or the existing 45-minute TTL. No re-sends, navigation, tab reopen, GET/history endpoint, or additional request.
2. Collect capture["assistant_result"] through driver.captured_assistant_response(capture) once the existing SSE response finishes. If unavailable, use await driver.observed_assistant_response() on the same current tab. Prefer completed, unambiguous SSE; never splice differing message/branch identities or downgrade complete results to partial. Stop observer on close.
3. Distinguish complete, partial, timeout, approval_wait, rate_limited, interrupted, unknown. Neither empty nor ambiguous response is complete. Preserve global backoff, send gap, connector approvals, and no-duplicate-send semantics.
4. Persist per-job-run in local SQLite only. Enforce 0700 parent dirs and 0600 database/WAL files, bounded content, no raw messages/URLs in logs, Matrix, and build output. UI refresh reads SQLite, never ChatGPT.
5. Preserve all owner-tab watchdog cleanup, independently enforced hard 45-minute TTL and main merge lock. Stage 3 uses Svelte read-only UI and only historical style references; Stage 4 covers full E2E and optionally one controlled canary.

## Offline tests

- uv run --no-sync pytest -q tests/test_response_capture.py tests/test_passive_network_capture.py
- bun tests/passiveResponseObserver.test.cjs
- Full validation before push: uv run --no-sync ruff check . ; uv run --no-sync ty check ; uv run --no-sync pytest -q ; bun run check

## Nox deployment requirement discovered during Stage 1

Nox uses setuptools strict editable mode. After adding new Python source modules,
plain uv sync --locked does **not** necessarily rebuild the editable import link
tree. Stage 1 initially failed worker startup with ModuleNotFoundError for
prompta.response_capture. Recovery was:

1. Run uv sync --locked --reinstall-package prompta in /home/brandon/prompta.
2. Verify import from .venv/bin/python before restarting the service.
3. If the service hit systemd's restart limit, reset-failed and start
   prompta-delivery-worker.service, then check ActiveState=active and NRestarts=0.

Repeat the explicit package reinstall whenever Stage 2/3 adds Python modules.
