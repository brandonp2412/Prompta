# ChatGPT-Web2API Roadmap

> **Status:** Active. Authored 2026-06-25 after a scope-correction review that
> removed work already shipped (honest `/health`, rate-limit retry) and moved
> `ensure` earlier because `/health` is already trustworthy.
>
> This document is the single source of truth for sequencing. Do not start work
> out of order without updating this file first.

## Guiding principles

- **Stabilize behavior before moving code.** The `cdp_driver.py` split (Phase 5)
  comes *after* the breaker policy (Phase 4). We instrument the monolith, prove
  the behavior is stable, then move it.
- **Lifecycle logic lives in the repo-owned CLI, not in hooks.** ZCode hooks are
  thin one-liners. Testable, idempotent logic belongs in `chatgpt-web2api ensure`.
- **REST owns Chrome. SSE attaches.** This invariant holds across every phase.
  Nothing else launches Chrome.
- **Don't re-scope shipped work.** If a phase's deliverable already exists in
  code, the phase is reduced to only its genuine gaps (see Phase 1 and Phase 4).

---

## Phase 0 — Merge PR #9  ✅ MERGED 2026-06-25

**Goal:** close the broad stabilization branch.

PR #9 (`fix/phase2-nontext`) — composer redesign, Phase-2 completion, tab
isolation — merged as squash commit `9ebb236`. All 9 CI checks green
(lint, secret-scan, build, 6× test matrix across ubuntu/macos/windows ×
3.11/3.12). The blocking tab-isolation concern raised in review was
**already resolved** in the branch: `owned` is the default tab mode, the
`adopt` path is gated behind explicit opt-in (`config.py`, `cdp_driver.py`).

### Pre-merge gates (all passed)

```text
pytest -m "not e2e"               ✅
ruff check .                      ✅
gitleaks / static gates           ✅
clean working tree                ✅
CI: 9/9 jobs SUCCESS              ✅
```

**Constraint honored:** no lifecycle / SSE / bootstrap work in PR #9. Those
start in Phase 2+.

---

## Phase 1 — Finish observability gaps

**Scope correction:** honest `/health` is **already shipped**
(`api_server.py:_handle_health`). It computes `chrome_running` and
`driver_connected` fresh on each call, returns all 8 fields, and distinguishes
`starting` / `healthy` / `degraded` / `broken`. Do not rebuild it.

### Remaining work only

1. **Regression tests for zombie states.** A process that is listening but not
   connected must not report healthy:
   - listener alive, Chrome alive, driver disconnected → `/health` returns
     `degraded`
   - listener alive, Chrome dead → `/health` returns `broken`
   - in neither case may `status` be `healthy` or `starting`

2. **Targeted debug logging for meaningful silent failures.** Many
   `except Exception: pass` exist (~20, mostly `cdp_driver.py`). Most are
   defensible best-effort cleanup, but several swallow errors that mask real
   failures. Add `logger.debug` (not warning — these are best-effort paths) at:
   - token refresh swallowed exceptions
   - heartbeat failure
   - CDP reader task exit
   - reconnect classification / skip decisions
   - tab registry reclaim / record / clear failures
   - best-effort cleanup failures (debug level only)

**Home for the silent-exception work is here, not split across Phase 5.** Phase 5
may move the code, but Phase 1 makes failures visible first.

---

## Phase 2 — Make SSE the recommended ZCode transport

**Goal:** replace stdio-per-session as the recommended mode. Eliminate the
process multiplier (N ZCode sessions × stdio = N MCP children × N tabs).

### Deliverables

1. **Document SSE config** (recommended):
   ```json
   {
     "chatgpt-web2api-sse": {
       "type": "sse",
       "url": "http://localhost:8090/sse"
     }
   }
   ```
2. **Document stdio** as compatibility / dev-debug mode only. Not recommended
   for many concurrent ZCode sessions.
3. **Integration tests** for SSE:
   - initialize handshake
   - list tools
   - list models
   - one chat call
   - repeated fresh connections (proves no tab/process growth)

### Reframed constraint

```text
Recommended ZCode mode is SSE-only:
  one persistent MCP server
  no per-session MCP child
  no per-session Chrome/tab spawning
```

The vague "detect many stdio processes and warn" item is **dropped from v1** —
under-specified, cross-cutting. Optional later.

### Known follow-up (discovered during Phase 0 verification, 2026-06-25)

```text
MCP/SSE chat_completion can complete server-side but timeout client-side on
response delivery. Short SSE tools work.
```

Reproduction: `initialize` OK, `tools/list` OK (9 tools), `list_models` OK
(1034 bytes returned). But `chat_completion` over SSE times out client-side
at 120s — while the send *did* reach Chrome and the reply appeared in the
account (conversation titled with the requested marker string). The REST
chat path returned the same kind of generation in ~2s.

This is a Phase 2 transport bug, **not** a PR #9 stabilization regression.
Track under Phase 2. Debug hypotheses to check: progress notifications
blocking, async generator never completing, MCP response never posted to
`/messages`, uvicorn/starlette SSE flush/backpressure, or a long-running
tool timeout mismatch.

---

## Phase 3 — Add `chatgpt-web2api ensure`

**Goal:** let ZCode hooks bootstrap the full stack with a thin one-liner.

### Command

```text
chatgpt-web2api ensure [--rest-port 8080] [--mcp-sse-port 8090]
```

Slots into the existing `{"start", "inject-cookies", "doctor"}` subcommand
dispatch in `__main__.py`.

### Contract

1. Check REST `/health`.
2. Reconcile REST per the **degraded-REST policy** below.
3. Wait until REST is healthy.
4. Check MCP/SSE on `:8090`.
5. If missing, start MCP/SSE.
6. Verify MCP/SSE: initialize succeeds + list tools succeeds.
7. Exit: `0` when ready, nonzero with clear diagnostic when not.

### Degraded-REST policy  *(PINNED — do not restart REST immediately)*

REST owns Chrome. Restarting REST runs `taskkill /F /T` on Chrome
(`chrome.py`) — visible window flash, 10–15s cold restart, may lose an
in-progress page. A naive restart on `degraded` is destructive flap.

```text
status=missing    → start REST
status=broken     → restart REST (Chrome is down; REST will relaunch Chrome)
status=degraded   → WAIT + re-poll first; restart only after repeated failed polls
status=healthy    → no-op
```

**v1 degraded policy:**

```text
degraded:
  poll every 2s for up to 20s
    if becomes healthy → continue
    if still degraded after 20s → restart REST
```

Reason: `degraded` (Chrome alive, driver disconnected) may be a transient CDP
reconnect. REST has reconnect logic (`dbc7985`); give it room before bouncing
the browser.

### SSE watchdog scope  *(PINNED — point-in-time, not continuous)*

`ensure` is a **point-in-time reconcile**, not a supervisor.

```text
ZCode hook runs ensure
  → ensure makes REST + SSE healthy NOW
  → ensure exits
if SSE dies later → next hook / next session reruns ensure
```

- Do **not** add a Python watchdog loop in v1.
- The SSE/MCP path currently has **no** crash-recovery (unlike REST's
  `start_monitor` for Chrome). This is acceptable for v1: SSE crash is rare and
  the hook re-runs on next session.
- Continuous supervision belongs in Phase 6 (optional OS-service docs), not here.

### Design constraints

```text
idempotent
lock-protected (lock files prevent duplicate starts)
safe to run repeatedly from ZCode hooks
no complex lifecycle logic in hook config
REST remains Chrome owner
MCP/SSE remains one persistent attaching process
```

---

## Phase 4 — Non-rate-limit breaker policy

**Scope correction:** rate-limit retry/backoff is **already substantially
implemented** in `resilience.py` (transparent retry, `Retry-After` respected,
jitter, `max_attempts=3`, dismiss-popup, persistent-limit escape → parseable
`RateLimitError`). Do not rebuild it.

### Remaining breaker classes

1. **Auth expired**
   - trip immediately
   - no retry storm
   - require human browser login
   - expose `auth_required`

2. **Composer / send-readiness**
   - one `navigate_new_chat` recovery attempt
   - trip after repeated failures (3 in 2 min)
   - cooldown 2–5 min

3. **CDP reconnect failures**
   - track repeated failed reconnects
   - cooldown before more send attempts (5 failures in 2 min → 2 min cooldown)

4. **Chrome crash loop**
   - track repeated Chrome restarts (3 in 5 min)
   - enter degraded/broken state with cooldown (5 min)

### Exposure

```text
/health          (breaker state in the response)
REST errors
MCP errors
logs
```

**Keep this before the big refactor (Phase 5).** Stabilize behavior first, then
move code.

---

## Phase 5 — Split `cdp_driver.py`

**Goal:** reduce bug density *after* behavior is stable. `cdp_driver.py` is
~2800 lines mixing CDP transport, ChatGPT DOM logic, completion detection, token
fetch, and tab registry.

### Suggested split

```text
cdp_transport.py        CDP websocket / session / reconnect
chatgpt_dom.py          composer / selectors / send-readiness
completion_detector.py  Phase-2 / action / end_turn / stall logic
backend_client.py       token / session / conversation fetch
tab_registry.py         (already split — validates the pattern)
driver.py               orchestration facade (stable CDPDriver API)
```

### Rules

```text
no behavior changes in the first split PR
move tests with modules
keep the public CDPDriver facade stable (no caller breakage)
```

---

## Phase 6 — Optional OS-level supervision docs

**Goal:** support always-on deployments outside ZCode. Comes last because ZCode
hooks are the primary path.

Docs only — no code:

```text
Windows Scheduled Task
NSSM / service wrapper
Linux systemd
macOS launchd
```

### Positioning

```text
ZCode users       → use the ensure hook (Phase 3)
always-on / server users → use OS supervision (this phase)
```

---

## Final sequencing

```text
0. Merge PR #9
1. Observability gaps: zombie regression tests + silent-failure logging
2. SSE recommended transport (docs + integration tests)
3. ensure command + ZCode hook docs
4. non-rate-limit breaker policy
5. split cdp_driver.py
6. optional OS-supervision docs
```

This version removes the stale health work, avoids duplicate rate-limit work,
drops the under-specified stdio-process warning, moves `ensure` earlier
(`/health` is trustworthy), and pins the two Phase 3 ambiguities (degraded
restart, SSE watchdog) before any `ensure` code is written.
