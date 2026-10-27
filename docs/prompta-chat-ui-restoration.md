# Prompta ChatGPT-like UI restoration — stage 1/16

Date: 2026-10-27 NZDT. Scope: historical UI audit, production ownership trace, desktop/mobile visual baseline, regression contract. No chat/reply implementation migrated in this stage.

## Predecessor and integration gate

- Project: `/home/brandon/prompta` on Nox. Baseline `main` = `origin/main` = `ac5fcc8e051474e3d31f44c27c2b27d968e262d8`, clean before baseline images. Existing worktrees for prior passive-capture/image tasks were found; no concurrent restoration edits were present.
- Prior passive response stages 1–4 are merged/pushed: `5fad648`, `3590005`, `8a85bca`, `596c178`, `a68a452`, `21f5411`, plus later `782e87b` capture fix and image-upload work through `ac5fcc8`.
- `docs/passive-response-stage4-handoff.md` records Nox release verification, 341 Python tests, strict checks, UI E2E, and local-only browsing. Systemd on Nox reports `prompta-ui`, `prompta-scheduler`, `prompta-delivery-worker`, `prompta-browser` active/running; `flaresolverr` is an additional independent service (name `flaresolverr`).
- Stage 1 adds this audit and narrow AGENTS authorization only. The active scheduler, queue, capture, database schema, Jobs UI, rate limits, browser profile, and service deployment remain unchanged.

## UI ownership and historical styling

| Surface | Production owner/source | `db709ee` styling to consider | Migration boundary |
| --- | --- | --- | --- |
| App shell/nav | `src/ui/App.svelte`, Jobs/Chats route query and popstate | Chat-first split layout with sidebar and main content | Prefer conversation list + detail while retaining Jobs as a first-class route; preserve browser/back history |
| Chat list/search | `src/ui/ChatsPage.svelte`, `resultFormatting.ts` | `SidebarList.svelte`: date groups, status dot, preview, selected row, timestamps, pin affordance, mobile long-press | Reuse spacing/typography only; derive results from LOCAL per-run rows, never account chat history |
| Transcript | `ChatsPage.svelte` detail and `ResultMarkdown.svelte` | `ConversationMessages.svelte`: readable aligned turns, muted timestamps, assistant identity, progress, compact message spacing | Current store has a job prompt + one final/partial assistant output, not a complete turn graph; never fake missing turns |
| Composer | Not present in production Chats UI | `Composer.svelte`: footer textarea, send interaction and attachment affordance | New manual-reply path must be explicit, branch-bound, durable and segregated from fresh scheduled jobs; no copy of old unrestricted send/retry pipeline |
| Jobs | `JobsPage.svelte`, `web_jobs.py` and `web.py` | `PromptaPage.svelte` used a backable jobs/control subpage | Preserve current Jobs CRUD, filters, Run once, images, and dashboard behavior; do not restore Machine Gun controls |
| Markdown | `ResultMarkdown.svelte` tokenized `marked` | Legacy `MarkdownContent.svelte` richer transcript presentation | Preserve escaped HTML, HTTP(S) links only, no remote image fetch on local view |

The historical `PromptaPage` also contained Machine Gun Mode and legacy account/history state. These are explicitly excluded. Legacy pin/unread behavior must not turn into account-wide reads or writes. Stage 1 used `git show db709ee:src/ui/{SidebarList,PromptaPage,ConversationMessages,Composer}.svelte` for visual and interaction reference only, without reverting any source.

## Backend/ownership trace

- `scheduler_service.DurableSchedulerProducer.enqueue_if_due` obtains one stable occurrence key/send ID and calls durable `DeliveryQueueStore.enqueue_idempotent`. Every scheduled occurrence remains a **fresh ChatGPT chat**.
- `delivery_worker._deliver_one` holds the delivery claim/lease, enforces ambiguity-safe dispatch and writes completion only after accepted send. `delivery_browser.BrowserSender` enforces global backoff/send gap, connector approvals, image refs, bounded 96-slot background passive capture, Once pinning and a unique capture lease. It never auto-replies.
- `response_capture.py` parses already observed conversation POST SSE and the same owned tab's semantic DOM; `playwright_driver.py` supplies those observations. No independent ChatGPT fetch is needed for passive response capture.
- `response_store.ResponseStore` owns private SQLAlchemy/SQLite WAL `job_responses`: send ID, prompt, answer, source, status, `conversation_id`, `message_id`, `parent_id`, timestamps and capture-owner/deadline. Writes reject branch changes and immutable terminal-state rewrites; recovery marks orphaned captures interrupted. States are queued/accepted/generating/completed/interrupted/unavailable.
- `web.py` exposes `GET /api/results`, `GET /api/results/{send_id}` and health/Jobs API. `ChatsPage.svelte` reads only these local endpoints on route change, filter/search and visible-tab 15-second refresh. There is currently **no manual reply endpoint or composer**. Browsing/search/refresh must stay entirely local.
- `browser_ownership.py` records `opened_at` for each owned tab; `browser_watchdog.py` and HTTP fallback expire after `opened_at + 45m`, with recovery after browser failure. **Gap for later stage:** new user requirement is 45 minutes since last verified activity (with an independent crash watchdog), not 45 minutes since open. Activity updates must be bounded and based on authenticated local ownership, not UI list browsing or polling. Explicit manual reply may reopen ONLY the exact persisted known branch; no speculative or unattended reopen.
- Automatic retries after any ambiguous submit remain forbidden. UI manual replies need independent user intent and exact-branch validation; no account-wide history, no tool/thought data, no raw private output in logs/Matrix/build artifacts.

## Production visual baseline (actual Nox-served UI)

Headless Chromium directly loaded `http://127.0.0.1:8765/`; no interaction with or focus theft from Brave. Screenshots are masked where job names/prompts/response text may be private and stored owner-only under `/home/brandon/.local/state/prompta/visual-baselines/stage1-20261027/` (0700 directory, 0600 PNG files).

| View | Desktop 1440×900 | Mobile 390×844 |
| --- | --- | --- |
| Jobs | `prompta-restoration-stage1-desktop-jobs.png` | `prompta-restoration-stage1-mobile-jobs.png` |
| Chats list | `prompta-restoration-stage1-desktop-chats.png` | `prompta-restoration-stage1-mobile-chats.png` |
| Selected chat | `prompta-restoration-stage1-desktop-detail.png` | `prompta-restoration-stage1-mobile-detail.png` |

All six PNGs were **opened and visually inspected**, not merely generated. Desktop uses a 360px-ish list rail with large blank detail pane until a run is selected. Mobile shows list and detail one at a time; `All chats` restores the list. No horizontal overflow at either requested viewport. Chat counts were 11 during capture, with status dots/pills and preserved NZ 12-hour times; large original prompts can push the assistant section below the initial viewport on mobile. Current Jobs default filtered view showed `Jobs 0` despite `26 configured jobs` all counted under `Long jobs 26`. Treat this as a baseline discoverability issue to review before changing filter semantics, not proof of lost jobs.

Network observation: 9 GET/0 POST (desktop) and 10 GET/0 POST (mobile); every request was to local `127.0.0.1:8765`. Repeated read-only interaction smoke (Jobs/Chats navigation, state filter, search no-match, refresh) likewise produced no POST and zero other hosts. Six completed rows were visible in the state filter at test time. No new ChatGPT prompt was sent.

## Regression matrix for stages 2–16

| ID | Invariant/check | Stage 1 evidence | Forward test obligation |
| --- | --- | --- | --- |
| R01 | Every scheduled run starts a fresh chat; Once pins only accepted run | scheduler/worker source, prior tests | Prove no scheduled reply-to-existing path |
| R02 | Explicit manual reply goes to exact known branch only | not implemented; stored identifiers reviewed | Check branch identity, user intent and mismatched/stale branch refusal |
| R03 | Chat list/search/detail/refresh use LOCAL data only | web source, live host audit | Assert zero ChatGPT requests during 15s refresh, pagination/filter/search |
| R04 | No account-wide history import or old-tab recovery on view | API/driver trace | Deny history GET and unsolicited navigation |
| R05 | Reap 45m after last activity, recover orphan/crashed tabs | existing open-time TTL identified | New idle clock tests + watchdog independent process/crash tests |
| R06 | No auto-resend after ambiguous submit | delivery state, queue | Fault-injection on submit acknowledgement loss |
| R07 | Global backoff/send gap/queue exactly-once preserved | scheduler/delivery ownership | Concurrent scheduled/manual sends under 429, restart and lease loss |
| R08 | Capture only final visible text and exact branch | observer/store | Tool/analysis suppression, branch rollover, partial/terminal immutability |
| R09 | DB SQLAlchemy WAL, migration, permissions | response store | File mode, fresh/old migration, lease races, no raw logs |
| R10 | Keep image upload for fresh jobs | image store and existing UI | Private path/prefix, preview visual tests, upload isolation |
| R11 | Preserve Once pinning and connector approvals | delivery browser | Controlled synthetic accepted send + approvals without duplicate |
| R12 | Preserve Jobs management/cadence | JobsPage/web_jobs/scheduler | Job CRUD, schedule intervals, fire-now semantics |
| R13 | Desktop/mobile readable, stable, accessible | six opened screenshots | 1440×900, 390×844; nav/back/scroll/composer keyboard; video/screenshots |
| R14 | Safe tokenized Markdown and no remote content | ResultMarkdown source | Raw HTML, unsafe link, remote image regression |
| R15 | All services/health survive deployment | systemd and Stage 4 handoff | Capture-aware safe rollout, health and watchdog before/after |
| R16 | Privacy and no focus stealing | redacted local screenshots/headless test | No raw content in logs/artifacts, no Brave foreground stealing |

## Test / deployment evidence

- Pre-existing Stage 4: 341 Python tests passed; Ruff, Ty, Bun/Svelte/Vite passed (see `docs/passive-response-stage4-handoff.md`).
- Stage 1 real browser E2E: desktop/mobile navigation, selection/back, search/filter/refresh, zero nonlocal hosts/POST, and visual inspection passed. Screenshots remain private.
- Strict buildq results: `#1294` Ruff **pass**; `#1295` Ty **fail, 34 diagnostics** in pre-existing application/test typing (including image-upload test response typing and fake browser driver protocol); `#1296` full pytest **353 passed, 1 skipped** in 82.03s; `#1297` Bun fmt/lint/TypeScript/Svelte/build **pass**. The generated `src/static/app.js` diff created by Vite normalization was restored to its pre-test tracked version; no production code edit remains.
- **Integration gate:** Ty is red on base `ac5fcc8` independent of this documentation/AGENTS change. No type rules, tests or code were weakened. Stage 1 proof is preserved but must not be declared fully validated or deployed until the baseline type failures are corrected and all checks rerun. Audit work is preserved on `audit/prompta-chat-ui-stage1-20261027`; Stage 2 should defer until this commit is validated and merged to `main` under lock.
- Nox Serena activation succeeded but every `serena_repl` query returned `INVALID_ARGUMENT / Unknown tool: serena_repl`; audit-only file reading and system/browser verification therefore used Nox Python MCP. No application code was changed through that fallback.

## Stage 2 handoff

1. Confirm this audit commit is in `main`, pushed, and Nox deployment/health remain good before mutating. If another restoration stage overlaps, defer under the shared main lock.
2. Design and test an explicit, branch-bound manual reply command/state machine and transcript record semantics. Preserve existing per-run answer records and privacy; don't auto-resume every captured job. No new account-wide ChatGPT browsing.
3. Specify precisely how activity gets refreshed for 45-minute idle reap, the independent watchdog's crash behavior, and how exact-branch manual reopen safely handles expired tabs and ambiguous send outcomes.
4. Preserve current scheduler/queue/jobs/health, images, approvals, FlareSolverr/backoff, and no Machine Gun/no unattended continuation. Use `db709ee` only as a visual reference.
5. Keep strict checks, real screenshots that are **viewed**, and append next-stage proof/commit to this same file. Integrate with `flock /home/brandon/prompta/.git/prompta-main-merge.lock` and safe Nox deployment.

## Stage 1 completion gate remediation (2026-10-27 NZDT)

This section supersedes the earlier red Ty integration gate; `#1295` is retained as historical evidence.

- Started from clean `main`/`origin/main` `b9cd577` after checking all five worktrees, buildq/pueue, and services. Created isolated `fix/prompta-stage1-gate-20261027` and merged audit `00d9649` under the shared main merge lock, preserving the newer security-challenge backoff. No overlapping restoration changes or running buildq tasks were found.
- Repaired all 34 strict Ty diagnostics in tests only: the shared fake driver implements `attach_images` and rejects unexpected attachments; image-upload tests narrow queue records, JSON mappings, strings, and lists; the architecture test reflects 45-minute idle reap and explicit exact-branch manual UI reopen. No `Any`, casts, type ignores, lowered strictness, or application code changes.
- Buildq final results: full Ruff `#1345` pass; strict Ty `#1346` pass (0 diagnostics); full pytest `#1347` **356 passed, 1 skipped** in 83.81 seconds; locked Bun install `#1339` pass; Bun format/lint/TypeScript/Svelte/Vite `#1340` pass. The old literal guardrail failure in `#1336` was repaired, targeted check `#1338` passed, and green full pytest includes it. The generated `src/static/app.js` diff was reversed.
- Real headless Chromium UI E2E at 1440×900 and 390×844 against local Nox server passed Jobs/Chats navigation, no-match search/clear, local refresh, selected detail, All chats/back, and no horizontal overflow. Each viewport issued **15 local GET, 0 POST, 0 nonlocal hosts**. No account-wide ChatGPT reads, new sends, or foreground browser interaction.
- Six privacy-masked screenshots were saved **and visually opened** under `/home/brandon/.local/state/prompta/visual-baselines/stage1-gate-20261027/` (directory 0700, files 0600): `prompta-stage1-gate-{desktop,mobile}-{jobs,chats,detail}.png`. Existing baseline design debts remain: 26 configured long jobs are excluded by the default filter (`Jobs 0`), and long prompts push the assistant block below the initial mobile viewport.
- Nox Serena activation succeeded, but `serena_repl` again returned `INVALID_ARGUMENT / Unknown tool: serena_repl`. Nox Python MCP with checked Git patches was the fallback; no private responses entered logs or artifacts.

Stage 2 handoff remains: only an explicit manual user reply can target an exact verified stored branch; scheduled runs always start fresh chats. Local results browsing cannot fetch ChatGPT history. Implement 45-minute idle activity tracking and independent watchdog, preserving queue, capture, images, security backoff, FlareSolverr, Jobs, and exactly-once safeguards. If this gate is not merged, pushed, and Nox healthy, repair/reschedule it and Stage 2 before Stage 3.
