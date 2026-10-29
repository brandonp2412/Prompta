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

### Integration and Nox post-deployment closeout

- Under the shared merge lock, fresh `origin/main` matched `b9cd577` and was a clean ancestor of the validated branch; main fast-forwarded to `c8e9b49027ca9215e1ae0c7725e762fa927a0291` and `git push origin main` succeeded. Audit `00d9649` is an ancestor of main; newer security-challenge fixes remain present.
- Production package reinstall via buildq `#1348` (`uv sync --locked --reinstall-package prompta`) passed; `prompta.web`, `prompta.scheduler_service`, and `prompta.delivery_worker` imports passed. UI and scheduler restarted independently under the merge lock. Browser and delivery-worker PIDs remained unchanged to preserve any owned-tab capture.
- Post-deploy `GET /api/health` returned HTTP 200, `ok: true`, `Cache-Control: no-store`; `GET /api/results` returned HTTP 200/no-store. UI, scheduler, delivery worker, and browser are all active. Git main remained clean.
- Post-deploy real headless Chromium re-smoke passed at 1440×900 and 390×844: respectively 15 and 14 local GETs, zero POSTs, zero nonlocal hosts, and no horizontal overflow. Six earlier privacy-masked screenshots remain saved and were visually reviewed; the re-smoke did not overwrite them.
- **Gate disposition: complete.** Stage 2 may proceed against deployed main once its worker verifies no overlap; Stage 3 must not preempt Stage 2. Keep this document updated with each later stage proof.

## Stage 2/16 — explicit reply contracts and verified idle leases (2026-10-28 NZDT)

### Gate and isolation

- Started from clean `main`/`origin/main` `31dca008`; Stage 1 audit `00d9649` and gate `c8e9b49` are ancestors, with the final Stage 1 deployed handoff at `31dca008`. All four Prompta services were active and `/api/health` was healthy. Checked all six worktrees, pueue, running processes, and the shared merge lock; no competing restoration work was present.
- Inspected historical `db709ee` composer for *styling only*. Nox Serena activation succeeded but `serena_repl` returned `Unknown tool`, so verified code patches used Nox Python MCP and `git apply`. Desktop Glass and interactive Brave remained untouched.

### Durable reply contract

- New `manual_reply_turns` SQLAlchemy/SQLite WAL table is independently migrated alongside existing `job_responses`, with owner-only database and WAL permissions. The existing scheduler/delivery queue and fresh-chat dispatch path are unchanged.
- Typed `ReplyIntent` requires an explicit idempotency key, nonempty text, and the exact persisted conversation ID plus current assistant message ID. The original run must be **completed** with complete branch identity. Replays of the same key/payload are idempotent; changed payloads, stale parents, unknown runs, and concurrent siblings are refused.
- A prepared intent is local persistence **only**, not a send. `POST /api/results/{send_id}/reply-intents` returns HTTP 202 with `dispatched: false`; `GET /api/results/{send_id}/turns` reads local records only. No composer, automatic worker pickup, browser navigation, or ChatGPT submission is wired yet. Stage 3 must implement explicit UI interaction plus verified branch/lease ownership before dispatch.
- The single atomic `prepared → dispatching` lease claim is irreversible. A lost acknowledgment or crashed dispatcher becomes `outcome_unknown`, never a silent resend. Accepted replies require exact conversation/parent/new message identity; only branch-matching final visible assistant text may complete a turn. Unresolved intents block descendants. The independent watchdog can recover stale dispatch leases without resending.

### Owned-tab idle lifecycle

- The existing owned-tab ledger now migrates `last_activity_at` from old `opened_at` data. Registering or navigating an owned tab does **not** reset activity. A currently owned and unexpired tab can refresh it only on confirmed acceptance or a new identity-bound captured response; expired tabs cannot be resurrected by a late touch.
- The passive-capture database lease and local capture deadline extend only after matching verified activity. The independent CDP/HTTP watchdog reaps tabs 45 minutes after their *last* verified activity, while marker fallback cannot overrule a newer lease; an unrelated driver does not preempt a live owner. Crash recovery remains independent of the delivery process.

### Checks and real UI evidence

- Buildq: full Ruff `#1377` **pass**; strict Ty `#1378` **pass, zero diagnostics**; Bun formatting, Oxlint, TypeScript, Svelte, Vite `#1379` **pass** (the pre-existing non-reactive `imageInput` Svelte warning remains); full pytest `#1382` **363 passed, 1 skipped** in 84.49 seconds. A first new idle-fixture assertion incorrectly tried to revive an already expired lease (`#1380`); fixed to refresh before expiry, reran targeted `#1381` and full `#1382` green.
- Real Nox headless Chromium E2E `#1384` at **1440×900** and **390×844** used the actual served Svelte/UI and private synthetic local runs. Tested Jobs/Chats navigation, selection/back, search/clear, explicit refresh, mobile responsive panels and horizontal overflow. **24 GET, zero POST, zero nonlocal hosts**; no ChatGPT conversation, browser focus, or scheduler action was invoked.
- Six owner-only PNGs were generated in `/home/brandon/.local/state/prompta/visual-baselines/stage2-20261028/` (0700 directory, 0600 files): `prompta-stage2-{desktop,mobile}-{jobs,chats,detail}.png`. **All six were opened and visually inspected.** Existing dark Jobs/Chats layout remained stable, mobile detail/back did not overflow, and the read-only UI remains unchanged. Known earlier debts are still outside Stage 2: the default Jobs filter can hide long jobs and long prompts can push mobile answers below the fold.
- No raw private prompts/answers in logs, Matrix, build artifacts or screenshots. Stage 2 does not enable unattended chat continuation or account-wide ChatGPT history reads.

### Stage 3 handoff

1. Add an explicitly user-triggered composer and route-specific intent creation only after showing the exact stored branch, its current assistant parent, and the prepared-versus-sent distinction. No automatic dispatch of stored `prepared` rows and no speculative old-chat browsing.
2. Wire a dedicated manual dispatcher behind account-wide backoff/send gaps, independent ownership leases, exact branch navigation verification, and a single irreversible pre-send claim; preserve scheduled *fresh* chats, Once pinning, image isolation, connector approvals, FlareSolverr, queue, health, and existing crash safety.
3. Extend per-turn UI and capture to show truthful partial/interrupted/outcome-unknown states; refuse ambiguous retries and mutated lineage. Test concurrent scheduled/manual dispatch, 429s, lease loss, process death, stale parent IDs, and independent 45-minute idle reaping.
4. Repeat full strict checks and exact-viewport real-browser screenshots, actually view them, then integrate under `prompta-main-merge.lock`, push and deploy Nox safely. Do not start Stage 3 before Stage 2 integration/deployment is fully verified.

### Integration and deployed Nox closeout

- Implementation commit `15d72abeb0206d5e73edb6ba0bc672d299e3ac86` fast-forwarded to `main` under `/home/brandon/prompta/.git/prompta-main-merge.lock`, pushed successfully, and verified against `origin/main`. No merge conflict or overlapping restoration worker occurred.
- Final pre-integration buildq gates: Ruff `#1385` pass, Ty `#1386` pass, full Bun/Svelte/TypeScript/Vite `#1387` pass, and pytest `#1388` **363 passed, 1 skipped** in 85.63 seconds. Normalized Vite output was reverted as test-only noise; no UI source changes.
- Nox package reinstall `#1389` succeeded. UI and scheduler were restarted. The delivery worker was restarted **only after** the single pre-existing passive capture reached its terminal state (zero active captures and no dispatch in flight). Browser service PID `725209` was preserved and remained active. No jobs were resumed by this work.
- Post-restart `GET /api/health`: HTTP 200, `ok: true`, no-store, browser reachable; `GET /api/results`: HTTP 200/no-store. All four services remained active.
- Actual post-deployment headless Chromium E2E `#1390` passed at 1440×900 and 390×844: **23 local GETs, zero POSTs, zero remote hosts**, no horizontal overflow, successful Jobs/Chats/search/refresh/back interactions and local turn API read. No ChatGPT sends occurred. Six earlier synthetic-private E2E screenshots were already opened and reviewed.
- Gate disposition: **Stage 2 complete, merged, pushed, deployed and verified**. Stage 3 may start with its explicitly user-triggered send bridge; Stage 2's prepared intent endpoint does not submit messages.


## Stage 3/16 — ChatGPT-style shell and unified local sidebar (2026-10-28 NZDT)

### Entry gate and scope

- Clean main/origin/main were both 8991ea9; Stage 2 implementation 15d72ab and its merged/pushed/deployed closeout were verified in Git and this document. All four Nox Prompta services and local health were active; worktrees and the free main merge lock were checked. No overlapping restoration worker was found.
- Inspected historical db709ee sidebar/Prompta page for styling ONLY. Nox Serena activation succeeded but serena_repl returned Unknown tool as in prior stages; Nox Python MCP applied checked Git patches instead. Desktop Glass/foreground Brave were untouched.
- This stage is UI-only plus a stronger layout guardrail test. Scheduler, delivery queue, capture, database schema, branch identity, reply dispatch, backoff, images, Once pinning, connector approvals and browser ownership code were unchanged.

### Shell/sidebar implementation

- Svelte 5 App now hosts a full-height desktop sidebar and content workspace; Jobs remains reachable and Chats detail/read-only views share navigation. Mobile uses a dismissible overlay drawer for Jobs/selected chats and a full-screen sidebar for an unselected Chats list, with Escape/back and no horizontal overflow.
- New chat opens the existing Jobs Run once form. Only an actual explicit user form submit queues one FRESH ChatGPT chat via the unchanged safe dispatch path. Merely opening does not send. Stage 2's exact-branch reply-intents remain local dispatched:false; no ChatGPT manual reply dispatcher was enabled here.
- Title/search, state filter, pagination, pinned group, unread marker, selected thread and NZ-local activity dates use only local /api/results and its exact send-ID detail endpoint. Within pinned/unpinned groups, latest updated_at (fallback created_at) sorts chronologically; read-state changes never reorder.
- Pin/read timestamps persist per browser in local storage as opaque Prompta send IDs and timestamps only (up to 24 pins; bounded reads). Off-page pinned metadata is hydrated using exact local result endpoints. No raw prompt/answer is stored in browser storage or logs.
- A 15-second visible-page local refresh updates lists and selected detail without changing selection. Jobs shows configured long jobs by default, fixing the baseline misleading Jobs 0 screen without affecting schedules.
- Replaced a brittle architecture assertion naming the old JobsPage location with checks for Jobs in the unified shell and forbidden remote chat actions; safety checks were not weakened.

### Strict verification and visual review

- Buildq #1399: Bun format, Oxlint, strict TypeScript, Svelte and Vite bundle PASS. Only the pre-existing Jobs imageInput reactivity warning remains. Reviewed production bundle src/static/app.js is included.
- Buildq #1402 full Ruff PASS; #1403 strict Ty PASS, zero diagnostics; #1401 full pytest 363 passed, 1 skipped (86.77s). Earlier #1394 failed solely on the superseded JobsPage location assertion; the strengthened new architecture test and full suite passed.
- Real Nox headless Chromium E2E buildq #1400 PASS at 1440x900 and 390x844: Jobs, Chats list/detail/back, selected thread, pin/reload, search/clear, refresh without selection jump, unread-to-read without reorder, mobile drawer/Escape, user-driven New chat -> Run once without submit. 44 local GET, zero POST, zero nonlocal hosts; no horizontal overflow.
- Six privacy-masked screenshots saved owner-only in /home/brandon/.local/state/prompta/visual-baselines/stage3-20261028/ (0700 directory, 0600 PNGs): prompta-stage3-{desktop,mobile}-{jobs,chats,detail}.png. ALL SIX were opened and visually inspected after final fixes. Names/prompts/answers were masked; no private text entered logs, Matrix or build output.
- Visual findings corrected: configured long jobs visible by default, selected local job title in header, inert mobile list-page close control hidden, and final mobile detail captured only after the intentional drawer animation settled.

### Stage 4 handoff

1. Preserve the shell, local-only search/read markers, selected-thread stability and Jobs access. Browser-local pins/read marks are presentation preferences, not account-wide ChatGPT state.
2. Manual replies still require a separate verified explicitly triggered dispatcher: exact stored branch/parent, independent leases, global gap/backoff, irreversible send claim and ambiguous-outcome refusal. Never drain prepared intents automatically or make scheduled jobs continue old chats.
3. Preserve private capture, statuses, image isolation, Once pinning, approvals, FlareSolverr, 45-minute verified-activity idle reap, crash watchdog and queue exactly-once. Repeat strict gates, real desktop/mobile screenshots, visual review, locked integration and safe Nox deployment.

### Integration and deployed Nox closeout

- Validated UI/source/test/handoff commit 16019ff475359eb4812f4e87af337f095f6f23b3 was committed on main and pushed to origin/main under the shared prompta-main-merge.lock after verifying the remote had not advanced. Main had no overlapping worker changes.
- Production package reinstall via buildq #1404 (uv sync --locked --reinstall-package prompta) passed. UI service was restarted under the merge lock, changing only its PID from 1643643 to 1691250; scheduler PID 1643648, delivery worker PID 1644467 and browser PID 725209 remained unchanged. All four service heartbeats were non-stale, browser reachable, and /api/health and private /api/results returned HTTP 200 (no-store for results).
- Actual POST-DEPLOY headless Chromium E2E buildq #1405 passed on the live service at 1440x900 and 390x844 with all sidebar, Jobs, selection, local search, pin/unread and mobile drawer assertions, 44 local GET / zero POST / zero nonlocal hosts and no horizontal overflow. Six privacy-masked desktop/mobile Jobs/list/detail PNGs were re-saved and ALL opened and reviewed after deployment.
- No scheduled jobs were resumed, no ChatGPT branch was opened, no manual reply was dispatched, and no browser-focus interaction occurred. The existing scheduler/delivery/browser ownership processes and exactly-once guards remained in place.
- Gate disposition: STAGE 3 COMPLETE, validated, merged/pushed and deployed. Stage 4 may start after verifying this closeout on current main and confirming there is no overlapping restoration worker.


## Stage 4/16 — Local multi-turn transcript (2026-10-28 NZDT)

### Entry and boundaries

- Verified clean `main`/`origin/main` at `d7a170c`, deployed Stage 3 `16019ff`, active Nox services, free merge lock and no overlapping restoration edits. Inspected `db709ee` **CSS only**; no legacy backend restoration. Nox Serena activation worked but the remote `serena_repl` endpoint returned `Unknown tool`, so checked Nox Python MCP edits were used as in Stage 3.
- The original Stage 4 Prompta fresh-chat run was accepted at 12:30 NZDT but stopped after its opening response with `cloudflare_challenge`. One owner-requested response retry failed `Unknown error`; no further retry or second prompt submission. The original run remains distinct from this locally executed remediation.

### Transcript UI

- The selected chat renders `/api/results/{send_id}/turns`, which reads *only* the private Prompta-generated SQLAlchemy SQLite WAL. The original job turn and any explicitly prepared/manual turns appear in durable order as separate user/assistant pairs, with Markdown, code blocks, copy actions, per-turn partial/accepted/prepared/dispatching/outcome-unknown/interrupted/completed states, and latest-reply status in the header. No thought/tool parts are rendered.
- Original fresh-job image attachments are previewed using only the existing validated local hashed-image endpoint; no new upload pathway or remote reads. Clipboard copy is triggered solely by user clicks. The detail view preserves an active scroll position on local refresh and follows growing content only if previously near the bottom. Failed turn reads show a warning and retain the locally known original result, not a false completed transcript.
- Reads are one concurrent pair of local detail + turns GETs per selection/15-second visible refresh; stale generations are discarded. No automatic ChatGPT history/navigation/reply, branch revival, tool approval, change to scheduler/queue/worker or resubmit was added. Mobile hides the offscreen sidebar from keyboard/accessibility until explicitly opened.

### Verification

- Buildq #1414 full Ruff PASS; #1415 strict Ty PASS; #1421 complete frontend formatting/Oxlint/TypeScript/Svelte/Vite PASS with the pre-existing `JobsPage.imageInput` warning unchanged. Buildq #1422 full pytest **364 passed** in 91.49 seconds; the new test checks two local user/assistant turns, long Markdown/code reply, hashed image preview, desktop/mobile layout, active scroll preservation and safe rendering.
- Real local Chromium E2E at exactly **1440×900** and **390×844** passed via #1420 and #1422; every observed browser request was to the synthetic localhost service. Screenshots are owner-only 0600 in `/home/brandon/.local/state/prompta/visual-baselines/stage4-20261028/`: `prompta-chats-desktop.png`, `prompta-stage4-mobile-top.png`, `prompta-chats-mobile.png`. All three were opened and visually reviewed; desktop roles and code controls, mobile first/second turns and long-response layout were sound. The white square in the synthetic fixture is a deliberate one-pixel white PNG, not a failed real preview.

### Stage 5 handoff

- Stage 4 is the local transcript/view layer only. Stage 5 must separately build the explicit user-triggered composer and verify actual browser manual dispatch with exact persisted conversation and current parent identities, irreversible claim, global backoff/send-gap, watchdog leases and no ambiguous retry. Never automatically drain prepared intents or reuse an existing chat for scheduled runs. Preserve FlareSolverr, passive capture, image isolation, connector approval policy, 45-minute inactivity reaping, crash recovery and exactly-once semantics.


### Stage 4 deployed closeout

- Implementation and tests committed/pushed to main as `8a3cfa7` with `origin/main` verified under `prompta-main-merge.lock`; no overlapping restoration edits or unresolved worktree merge. Postscript browser GET-only proof buildq #1423 PASS.
- Production reinstall buildq #1424 (`uv sync --locked --reinstall-package prompta`) PASS. Restarted **only** `prompta-ui.service` under the merge lock: UI PID `1691250 → 1982661`; scheduler `1643648`, delivery worker `1644467`, browser `725209` unchanged. `GET /api/health` returned HTTP 200 with `ok:true`; `GET /api/results?limit=1` returned HTTP 200, `Cache-Control:no-store`. No jobs were resumed or re-sent.
- Actual deployed private localhost Chromium smoke passed at 1440×900 (10 GETs) and 390×844 (9 GETs); zero POSTs, zero nonlocal hosts, no horizontal overflow, transcript loaded. Saved `stage4-live-{desktop,mobile}-masked.png` owner-only 0600; both opened and visually reviewed with private content masked. The synthetic E2E was likewise visually reviewed in three unmasked fixture screenshots.
- The original browser-owned Stage 4 run reached its 45-minute watchdog terminal `interrupted` state at 13:15 NZDT after Cloudflare/unknown tool-response errors; it was **not** marked successful, resubmitted, or continued. This distinct manual remediation completed its requested code stage. Stage 5 queued at 13:15 behind Prompta's existing security-challenge backoff until 13:31:11 NZDT and must verify this deployed commit before proceeding.
- Gate disposition: **Stage 4 implemented, fully tested, integrated, deployed and inspected**. The original failed scheduled conversation remains truthfully interrupted; no ambiguous resend.


## Cloudflare auth probe remediation (2026-10-28 NZDT)

- Live Nox diagnostic: the Prompta Brave profile has a `cf_clearance` cookie and can display an existing authenticated homepage, but a single `/api/auth/session` request returned HTTP 403 with `cf-mitigated: challenge`. FlareSolverr v3.5.2's two approved homepage-only GETs (12:31 and 13:31 NZDT) both reported "Challenge not detected", returned no new clearance, and did not solve the auth endpoint challenge. A reversible isolated browser-service switch to stock Chromium also received a 403 on fresh navigation; it was rolled back to the exact original Brave service and repository config. No queued prompts were resent or cooldowns reset.
- The old `ensure_token.js` incorrectly parsed challenge HTML as JSON and hid the Cloudflare response, then retried the authenticated session endpoint every 0.5 seconds for up to 30 seconds. It now identifies `cf-mitigated: challenge` before parsing, exposes only a boolean (not cookies, tokens or body), and raises a typed security challenge. `connect` invokes its existing once-per-cooldown homepage-only FlareSolverr path and then fails closed to durable security backoff if no valid clearance is obtained; transient non-challenge auth checks are spaced five seconds apart. No history/results, blind retries, extra browser requests or unattended continuation were introduced.
- Buildq #1429 Ruff PASS, #1430 strict Ty PASS, #1431 full pytest 365 passed / 1 skipped (83.19s), #1432 frontend format/Oxlint/TypeScript/Svelte/Vite PASS (only the pre-existing `imageInput` warning). A separate Bun execution proved the actual JS probe recognizes a synthetic HTTP 403 challenge before attempting JSON parsing.
- This is a rate-limit and recovery-safety fix, **not a Cloudflare bypass**. A genuine unsolved challenge still requires the owner's authorized verification in the actual Prompta browser session; no login details or account-wide data are given to FlareSolverr.


### Cloudflare auth probe deployed closeout

- Commit `0adc00e` pushed to `main` under the shared merge lock. Buildq #1433 production package reinstall passed. Delivery worker restarted from PID `1644467` to `2006904` only after proving zero live capture leases or running delivery leases; scheduler and browser PIDs remained unchanged, and neither the browser profile nor current cooldown was reset.
- Stage 5 (`prompta-chat-ui-05-compose`) remained queued with no new attempts. Existing security-challenge backoff remains until 15:31:13 NZDT. The real Cloudflare 403 is still externally controlled and has **not** been bypassed; do not force another prompt attempt or mistake this fail-fast remediation for clearance.

## Persistent FlareSolverr browser handoff (2026-10-28 NZDT)

- A dedicated Nox user service `prompta-flaresolverr` runs Chromium on private X display `:99` and local port `8193`, isolated from the existing shared FlareSolverr `8191` and the Prompta-owned Brave CDP browser. `sessions.create` reuses the fixed `prompta-chatgpt` session; only its private browser profile persists on disk across service restarts (`~/.local/state/prompta/flaresolverr-chrome`, owner-only). FlareSolverr source patch is committed in the installed `v3.5.2` checkout.
- Prompta's recovery client uses that exact session for one cooldown-limited ChatGPT homepage GET, transfers only `cf_clearance`/UA on success, and never sends account cookies, chat/history GETs or prompts through FlareSolverr. No queued job is automatically resumed or duplicated. This integration does not guarantee Cloudflare accepts clearance in Brave; verify only after owner login.
- Temporary TLS VNC `prompta-login-vnc` exposes X display `:99` on Nox LAN `192.168.1.133:5903` with an owner-only password file. Disable VNC after owner authentication. No VNC password is stored in the repository.


## Stage 5: responsive composer and explicit fresh/reply sends — gated handoff (2026-10-28 NZDT)

- **Predecessor and exclusion gate:** Stage 4 `8a3cfa7` / deployed closeout `0773167` was already merged, pushed, deployed and visually verified. Stage 5 began from clean, synced `main` `5d0facb` in separate worktree `/home/brandon/.worktrees/prompta-chat-ui-stage5-20261028`, branch `stage5/chat-composer-20261028`. No restoration edit was in flight, and the production main tree was never edited. Read `AGENTS.md`; inspected legacy `db709ee` only for styling. The legacy commit supplied no CSS worth transplanting.
- **Feature:** A desktop/mobile bottom composer handles focus, Enter send / Shift+Enter newline, disabled and ambiguous-send states. Fresh chats support an existing private image endpoint (file picker, drag/drop, paste, max four PNG/JPEG/GIF/WebP images of 8 MiB each), preview/remove controls, and a single explicit `POST /api/chats` with a payload-bound 128-bit request ID. That call enqueues the existing durable delivery queue as a **new ChatGPT chat**; it cannot mutate a scheduled job or automatically continue an old branch.
- **Exact-branch reply:** An explicit UI `POST /api/results/{send_id}/reply-send` creates one durable manual reply intent; no prepared intent is auto-drained. It is eligible only after a *completed local* result has both ChatGPT conversation and last-assistant message IDs, verified again against the visible owned tab's URL and last assistant DOM identity. A single irreversible claim and SQLite `BEGIN IMMEDIATE` account-wide 45-minute send reservation precede one browser click. The worker observes only that owned tab's POST/SSE and semantic DOM, checks returned IDs, preserves connector approval, refreshes verified leases up to the 45-minute inactivity watchdog, and leaves missing/ambiguous outcomes `outcome_unknown` or `interrupted` with **no retry**. Orphaned active manual leases are reconciled on UI startup and health ticks. Other scheduler/queue, Once pinning, backoff, passive capture, images, FlareSolverr and Jobs UI paths remain in place; no account-wide history reads, Machine Gun, raw-response logging, or focus changes.
- **Test evidence:** buildq #1583 focused UI/backend 36 passed; #1586 Bun formatter/Oxlint/Svelte/TypeScript/Vite PASS (one pre-existing `JobsPage.imageInput` reactivity warning); #1587 full strict `pytest -q` 378 passed in 100.58s, using actual Chromium. Post-hardening full repeat buildq **#1589 passed 378 tests in 99.42s**. Ruff and strict Ty passed after the final hardening; `git diff --check` passed. Tests exercise HTTP idempotency, modified-key rejection, keyboard send/Shift+Enter, drag/drop/paste, synthetic attachment receipt, mobile layout/no x-overflow, a single UI POST, an exact-branch fake browser send/stale branch refusal, and concurrent send-window reservation. Synthetic real Chromium screenshots were captured at **1440×900** and **390×844** with no nonlocal requests. No fake ChatGPT request is described as a live send.
- **Screenshots:** owner-only `0600` at `/home/brandon/.local/state/prompta/visual-baselines/stage5-20261028/`: `stage5-1440x900-composer.png`, `stage5-390x844-composer.png`, `stage5-1440x900-reply.png`, `stage5-390x844-reply.png`. All four were opened and visually reviewed: stable bottom composer, keyboard labels, three attachment thumbnails, clear send affordance, narrow-screen wrapping and reply transcript, without horizontal overflow. Test content is synthetic.
- **Production blocker and gate disposition:** At the production read-only checkpoint ~21:18 NZDT, **0/12 completed local job runs contained a persisted ChatGPT `conversation_id`**, despite local message IDs; thus no eligible exact-branch reply existed. A live reply could not be verified without guessing an identity or reading account history, neither authorized. One browser-owned delivery capture was still active and the shared 45-minute send gap was in effect. No extra production job was queued or sent for testing, no ambiguous POST was retried, and no worker/tab with an active capture was restarted. **Stage 5 is feature-implemented and synthetic-E2E validated but is NOT live-send validated; main integration and Nox deployment are deliberately deferred.**
- **Committed preservation:** Feature implementation and this evidence were committed as `7cd5926123593f41f85a766b3b48654816fe2e8d` and pushed to `origin/stage5/chat-composer-20261028`. No `main` merge or production restart was performed. Final read-only production check (~21:31 NZDT) remained **0/12** completed results with a conversation ID; all 12 completed records had `source=dom`, empty `parent_id`, and a DOM message identity. DOM fallback intentionally does not infer a conversation/parent ID; the displayed assistant unit may group multiple real message IDs, so it cannot be guessed into an exact reply target. Queue held 12 retrying and one queued delivery, so no live exact-branch send was attempted.
- **Next-stage gate:** Keep Stage 6 paused; a future owned delivery capture must persist an unambiguous completed conversation ID and last assistant ID from its own POST SSE or same-tab semantic DOM. After the global cooldown and any active lease clear, explicitly send a single manual reply from Prompta UI to exactly that verified branch and prove its one POST and completed local turn; also prove one fresh UI chat traverses the durable queue to one new ChatGPT conversation without changing scheduled jobs. Re-run strict full tests and both viewport E2E, inspect screenshots, then take `prompta-main-merge.lock`, recheck `main`/origin and live leases, merge/push/deploy safely. Do not reset a send gap, inspect account-wide history, steal browser focus or claim this partial gate was completed.


## Stage 5 reintegration and restoration-job repair (2026-10-29 NZDT)

- Owner requested removal of the repeated restoration deferral cycle. Nine exact one-time gated recheck jobs for Stages 6–10, 12, 14, 15 and 16 were removed through the supported Prompta CLI after matching their names in the local scheduler DB. Definitions were preserved privately in owner-only `~/.local/state/prompta/restoration-deferrals-removed-20261029.json` (0600), and a postcheck found no `prompta-chat-ui-*` schedules; all other scheduled jobs were unchanged. This did not cancel, retry or resume queued sends.
- Started from clean synchronized `main` `f8288fe` in isolated worktree `fix/stage5-reintegrate-20261029`, preserving original pushed Stage 5 `c1c6403`. Reconciled five merge conflicts against newer scheduler, Once opt-in pinning, concurrent passive capture and mobile styling. Kept main's removal of the artificial global dispatch gap while retaining durable global rate-limit backoff and the manual reply store's irreversible SQLite claim; a concurrent two-worker regression test proves only one claim succeeds.
- Fixed the fresh chat request ID's pinned Once `manual:once:` client-key compatibility, preserving immutable payload idempotency. Fixed a missing CSS media-query close brace discovered by actually viewing the first 1440×900 desktop screenshot; added computed-style and composer bottom-anchor assertions for both viewports. Modern exact-branch verification now parses a *single* JSON-encoded `data-chatgpt-search-message-ids` backend UUID instead of whitespace splitting; rejects multiple, malformed and mismatched IDs. Five real Chromium branch-probe fixtures use an intercepted local synthetic page with zero external network access.
- Buildq #1824 Stage 5 focused tests PASS; #1825 frontend PASS; #1826 Ruff PASS and #1827 Ty PASS. Initial full #1828 exposed a legitimate Once pinning idempotency regression; corrected it, and #1829 affected-suite PASS. Full #1830 PASS. Real Chromium composer/reply E2E #1832 PASS; all four refreshed synthetic 0600 PNGs in `~/.local/state/prompta/visual-baselines/stage5-integration-20261029/` were actually opened and reviewed at 1440×900 and 390×844. New exact-branch Chromium test #1836 PASS. Final full real-Chromium suite buildq #1837 **405 passed** in 114.18s; #1838 complete frontend format/Oxlint/TypeScript/Svelte/Vite PASS; #1834 strict Ty and #1835 Ruff PASS. No weakened test gates.
- Pre-deploy live read-only check: `GET /api/health` HTTP 200, UI/scheduler/delivery active, independent browser-watchdog timer active, browser page count 1 after reaping, zero queue pending, zero active nonterminal capture leases. Main and origin/main stayed synchronized while the isolated candidate was tested; no production changes, ChatGPT sends or manual replies from these tests.
- Live exact-branch user reply remains a separate production acceptance check: current completed local response rows did not expose a complete conversation + assistant parent identity pair. The new manual endpoint refuses such rows instead of guessing or reading ChatGPT history. Do not claim a real ChatGPT manual reply succeeded on the basis of the intercepted synthetic tests. A future explicit owner UI send to an exactly verified stored branch is required to prove live acceptance; never blind-retry an ambiguous send.


### Stage 5 production deployment and verified UI closeout (2026-10-29 NZDT)

- Merged and pushed Stage 5 reintegration commit `1af9ee4f080e1f8c5198dd467424193059c77a28` into clean synchronized `main` while holding `prompta-main-merge.lock`. Buildq #1839 production `uv sync --locked --reinstall-package prompta` PASS. Checked zero active delivery/capture/manual dispatch leases and zero pending delivery queue items before restarting **only** `prompta-ui.service` (PID 2673957 to 2722362); worker, scheduler and browser service were left running. `GET /api/health`, `GET /api/jobs`, `GET /api/results?limit=1` returned HTTP 200 with private `no-store` data endpoints. No production message was submitted, replayed or retried.
- Post-deploy real localhost Chromium UI smoke through buildq #1845 PASS at exact **1440×900** desktop and **390×844** mobile. Navigated locally captured chat list, new-chat composer and Jobs; each viewport made 18 local GET/HEAD requests and **zero POST or remote requests**. Asserted visible composer/Run once controls and no horizontal overflow. Six 0600 owner-only, private-content-masked screenshots in `~/.local/state/prompta/visual-baselines/stage5-live-20261029/`: `live-1440x900-{list,new,jobs}-masked.png` and `live-390x844-{list,new,jobs}-masked.png`. **Actually opened and reviewed all six:** desktop sidebar/content alignment, bottom-anchored new composer, mobile centered new-chat state, mobile chat list, and Jobs count/action wrapping were sound. The Jobs UI reported four healthy non-restoration configured jobs; removing the nine `prompta-chat-ui-*` deferral schedules did not remove these other jobs.
- Final disposition: repeated restoration-stage deferral jobs are removed; feature and safety checks are integrated and deployed. A **12-hour soak and real external ChatGPT reply/revive/attachment acceptance test have not been demonstrated**; the available completed local results still lack the exact verified branch identities required for a live reply. This is an honest remaining test requirement, not permission to guess IDs, scrape account-wide history, bypass Cloudflare, or blindly retry an ambiguous submit. All future scheduled deliveries must create fresh chats; manual branch revival requires an explicit UI action and verified exact branch.


## Correction: Stage 6–16 restoration schedules restored (2026-10-29 NZDT)

- The earlier 2026-10-29 decision to remove nine gated recheck jobs was incorrect: it deleted the remaining restoration-stage execution schedule instead of repairing the deferral causes. At the owner's subsequent objection, recovered all nine from private owner-only `~/.local/state/prompta/restoration-deferrals-removed-20261029.json` with the supported `prompta at` CLI, retaining their original exact one-shot UTC epoch run times and identical prompts. This reversal **supersedes** the earlier 'deferral jobs removed' operational state; retain that earlier entry solely as an audit trail.
- Verified each restored row against the archive: all nine present, every original prompt byte-identical, zero run-time drift, one-shot interval `0`; the four unrelated daily maintenance jobs survived unchanged. The live `/api/jobs` API reports **13 configured jobs** and `/api/health` reports HTTP 200 `ok:true`; SQLite `PRAGMA quick_check` returned `ok`. Earliest restored Stage 6 run is **2026-10-29 23:00:35 NZDT**. No prompt send or queued delivery was initiated by the restoration itself.
- The gate root cause is not magically resolved by schedule restoration: Stage 6 requires a completed run carrying both an exact verified ChatGPT conversation and last assistant identity, and production previously lacked such a pair. Recheck genuine capture evidence and implement a safe fix if needed; never guess a branch, scrape account-wide history, auto-reply, override backoff or blindly retry an ambiguous submit. Every scheduled stage run must start a fresh chat; only a separate explicit owner UI reply may revive a verified branch.


## Accelerated shared Prompta stage cadence (2026-10-29 NZDT)

- Owner asked to increase the cadence of the stage jobs. Discovered 30 separate `prompta-mobile-ux-v2-*` one-shot stages alongside nine restored `prompta-chat-ui-*` stages. Changed only these 39 scheduled stage entries, leaving four existing recurring maintenance jobs and their 168-hour intervals untouched.
- Assigned all 39 stages one common `prompta-ui-stage-work` scheduler mutex group to avoid overlapping pending delivery work across both stage streams; each remains a one-shot fresh ChatGPT chat, with its prompt, image metadata, Once pin flag and source revision unchanged. Applied staggered global slots **105 minutes apart** beginning 2026-10-29 10:45 NZDT, preserving ordering within each stream. Stage 6 begins 2026-10-29 23:00 NZDT, Stage 15 is planned for 2026-10-31 04:45, Stage 16 2026-10-31 20:30 (15h45 later, respecting the *planned* 12-hour post-release soak), and the final mobile stage for 2026-11-01 05:15 NZDT. Actual Stage 16 soak must be measured from real release/deployment, not merely schedule arithmetic; if prerequisites are late, it must wait and report honestly.
- Backed up all previous stage timestamps and mutex metadata in owner-only `~/.local/state/prompta/cadence-before-20261029-1040.json` (0600) before a single SQLite transaction updating both `scheduled_jobs.run_at_epoch` and the scheduler's persisted `initial_due_at_epoch` state atomically, avoiding stale due markers. Verified all 39 due markers/mutexes, SQLite `PRAGMA quick_check: ok`, live `GET /api/jobs` HTTP 200 with **43** configured entries and matching Stage 2/Stage 16 times. Buildq #1851 focused scheduler/resource-admission/delivery-intent/Jobs tests **66 passed in 26.46s**. No ChatGPT submits, restarts, queued deliveries, or private responses were touched by the rescheduling itself.
- A faster cadence does not waive predecessor completion, main merge locks, security-challenge backoff, exact-branch reply verification, or no-ambiguous-retry invariants. The shared mutex prevents concurrent *pending deliveries*, and each stage must still verify no overlapping repository edits and predecessor merged/pushed/deployed before touching code. Delayed real completion can move the effective stage sequence; do not misrepresent planned timestamps as completed milestones.


## Auckland waking/night stage concurrency, deployed (2026-10-29 NZDT)

- Owner clarified a *time-varying admission ceiling* for all 39 `prompta-ui-stage-work` jobs: **one ongoing stage during 07:00–22:29:59 NZ local time**, **up to three from 22:30 through 06:59:59**. The next stage may launch only when the corresponding cap has an available slot. At 07:00, already-accepted captures are not interrupted or forcibly terminated; new admissions wait until the active count falls below the daytime cap. Four unrelated maintenance jobs retain their independent scheduling. The IANA `Pacific/Auckland` zone handles NZDT/NZST transitions.
- Prior single-mutex implementation looked only at configured scheduled-job rows and pending delivery receipts; this was insufficient because a one-shot job is removed from `scheduled_jobs` immediately upon enqueue, and an accepted delivery receipt becomes terminal while its separate passive capture remains active. The new stage admission uses the **union of distinct queued/running/retrying/rate-limited scheduled send IDs and live accepted/generating result-capture leases**, by the two exact stage job prefixes. It never reads private response bodies, account-wide ChatGPT history, or a different browser tab. Ordinary non-stage mutex behavior, rate-limit backoff, passive capture, explicit manual branch replies, exactly-once semantics and 45-minute idle reaping remain unchanged. One delivery worker may accept fresh chats serially while separate owned-tab passive captures continue concurrently; a three-slot *cap* does not force independent predecessor-dependent stages to start simultaneously.
- Feature commit `ffcf985e4d3ecfaecec92323a85a6d523a3f0550` fast-forwarded and pushed to `main` under `prompta-main-merge.lock`. Buildq #1852 focused scheduler tests PASS; #1857 full pytest **402 passed / 11 skipped** without Chromium; #1862 full real-Chromium pytest **413 passed in 114.86s**; after minimizing unrelated formatting, #1867 Ruff, #1868 strict Ty and #1871 focused tests PASS, `git diff --check` PASS. Tests assert exact 22:30/07:00 boundaries, winter NZST, 3-at-night/1-by-day, stage one-shot row removal, accepted capture continuing after queue receipt completion, and safe dawn admission contraction. No ChatGPT sends were made by tests.
- Buildq #1872 `uv sync --locked --reinstall-package prompta` PASS. With the next stage not due until 12:30 NZDT, restarted **only** `prompta-scheduler.service` (PID 2673971 -> 2779815); the delivery worker PID 2689076 and UI PID 2722362 stayed unchanged, preserving one active mobile-stage capture. `GET /api/health` HTTP 200 `ok:true`; `GET /api/jobs` HTTP 200 reported 42 remaining entries (one stage had already been legitimately enqueued and its one-shot schedule removed). A read-only probe through the production-installed package found `stage_parallel_limit(now)==1`, and the next stage's admission blocked by the already-live capture. Simulated 22:29:59/22:30/06:59:59/07:00 production code boundaries resolved to **1/3/3/1**. No queue item was replayed and no worker, browser, UI or live tab was restarted.
- The existing 105-minute staggered stage slots are retained. This is a maximum number of simultaneously outstanding stages, **not** a promise to run three dependent mobile or restoration stages before predecessor integration. Every stage still verifies the predecessor merged/pushed/deployed, no overlapping repository edit, a clear merge lock, and its own result evidence; if an external rate limit or ambiguous submission blocks a stage it remains fail-closed without a blind retry.


## Corrected to opt-in per-install stage concurrency setting (2026-10-29 NZDT)

- The earlier code-constant 07:00–22:30 cap=1 / 22:30–07:00 cap=3 was an inappropriate global implementation. Feature commit `bf679b61810c5f1791322d795db8c9950fe18e7b` replaces it with **optional, validated `[stage_concurrency]` TOML configuration** under the existing per-user `~/.config/prompta/config.toml`. The section is *absent/disabled by default*: other users have **no special time-of-day parallelism ceiling**, while explicit per-job mutex groups continue to perform their normal opt-in mutual exclusion. Users can configure IANA timezone, HH:MM night boundaries, positive day/night limits and stage job-name prefixes without a source edit. Config file inode/mtime/size changes reload on the next relevant scheduler admission; malformed enabled settings raise an error and do not silently drop a limit.
- This Nox user alone opted into prefixes `prompta-chat-ui-` and `prompta-mobile-ux-v2-`, timezone `Pacific/Auckland`, `night_start=22:30`, `night_end=07:00`, `day_limit=1`, `night_limit=3`. Prefix admission includes future one-shot stage jobs even if created by the CLI without a mutex group; active captures already admitted continue safely through a dawn limit contraction. The previous user config was preserved privately as `~/.local/state/prompta/config-before-stage-parallelism-20261029.toml` (0600). Wrote the new live config atomically, owner-only 0600, preserving the exact existing `working_hours` and `connector_approval` policy values. Documented opt-in example in README.
- Buildq #1885 and #1896 focused config/admission tests PASS, #1897 full Ruff PASS, #1898 strict Ty PASS, #1899 **425 real-Chromium pytest tests passed in 121.13s**; `git diff --check` PASS. Tests prove absent/disabled means no special cap, 1/3 Auckland wall-clock rules including NZST, hot-reload without restarting producer, future stage job without mutex metadata, and fail-closed validation. No test touched real ChatGPT sends or private responses.
- Pushed feature into clean synchronized `main` under `prompta-main-merge.lock`; buildq #1901 Nox locked package reinstall PASS. Restarted **only** `prompta-scheduler.service` (PID 2779815 to 2813925); delivery worker 2689076 and UI 2722362 unchanged, preserving passive capture. Live `GET /api/health` returned HTTP 200 `ok:true` and `/api/jobs` returned 42 remaining entries (Stage 1 had already been legitimately queued as a one-shot). A read-only probe in the installed production environment verified enabled user config, the absence-default unlimited special cap, scheduler cache matching the live setting, and exact Auckland boundary outputs **1 / 3 / 3 / 1** at 22:29:59, 22:30, 06:59:59 and 07:00. The next stage was still scheduled at 12:30; no queue item was replayed or tab reopened.
- Concurrency remains an *admission maximum* based on distinct pending stage deliveries and active local capture leases, not a guarantee of three independent code changes. Stages still honor predecessor merge/deploy gates, repository exclusion lock, backoff and no blind retry after ambiguous sends. No other users or maintenance jobs acquired the Nox-specific cap.


## Passive tool-call capture and local transcript (2026-10-29 NZDT)

User-authorized exception to the prior tool-data suppression: only tool calls emitted by the
**existing owned conversation POST** are eligible for private, bounded capture. No independent
GET, history import, browser navigation, or scheduled reply is added. Hidden reasoning, raw SSE
frames and credentials are not stored; structured argument/result previews have field-key
redaction, size and count caps. Ambiguous final branches discard tool details together with
assistant text. Existing plain-text conversations remain supported.

- `ToolEventCollector` deduplicates SSE invocation snapshots, understands path/args and combined
  `mcpToolCall` forms, pairs subsequent tool messages where identifiable, and preserves call order.
- `CaptureResult.tool_calls` passes display summaries through the established single-run capture
  boundary. The active owned-tab capture briefly waits for its already-issued POST response when
  DOM finality arrives first. No extra HTTP request or cross-branch merge is allowed.
- SQLAlchemy/Alembic adds `tool_calls_json` to existing job and manual-reply rows with legacy
  `[]` defaults, retaining private WAL permissions, branch checks, and exactly-once state rules.
  `/api/results/{send_id}` and `/turns` expose the same structured data from local SQLite.
- Chats renders a compact expandable tool timeline, individual connector/action/status cards,
  redacted inputs/outputs/errors, and the original final Markdown separately. Mobile remains
  touch-friendly; static historical rows without tool fields keep their original rendering.

Verification: `tests/test_tool_events.py` covers a complete synthetic owned SSE POST through
private storage and local turn retrieval, duplicate invocation events, combined MCP messages,
redaction and ambiguous branch isolation. `test_tool_cards_desktop_mobile_local_only` exercises
real Chromium at 1440×900 and 390×844 against an isolated local HTTP server, including detail
expansion, error styles, final answer, zero nonlocal/POST requests and screenshots. Full test,
strict type/lint and Nox deployment results are recorded with the integration commit.


### Rebased validation evidence

- Rebased onto `eb15737` (exact stored-parent manual reply recovery); only generated
  `src/static/app.js` conflicted and was rebuilt from the combined Svelte sources.
- Buildq `#2100` Ruff passed, `#2101` Ty strict passed, `#2102` Bun fmt/lint/TypeScript/
  Svelte/Vite passed, `#2103` isolated Chromium E2E passed, `#2104` full pytest
  **434 passed, 20 skipped** in 177.89 seconds.
- Real Chromium screenshots at 1440×900 and 390×844 are private under
  `/home/brandon/.local/state/prompta/visual-baselines/tool-events-rebased-20261029/`.
  The initial synthetic screenshots for both viewports were opened and visually reviewed:
  tool badges, expanded input/output, failed state, final Markdown, narrow widths and
  composer layout were checked. Browser test confirmed all network requests were local
  GETs and zero POSTs. No real ChatGPT conversation was fetched or sent for this test.
- Live-event ingestion after service deployment still requires a natural owned job with
  structured tool events; the deterministic E2E proves parser→SQLite→API→browser.


## Structured tool-call capture integration verification (2026-10-29 NZDT)

- Reconciled the isolated tool-call feature against the then-current chat composer, local SQLite pinning, response recovery, queued-chat UI and server-backed reply branch checks without reverting them. Capture stays restricted to the already-owned conversation POST/semantic DOM; local chats listing/refresh issues no ChatGPT history or account-wide requests. Only explicit tool invocation/result metadata is stored; internal reasoning is excluded. Arguments/results are bounded and structured private fields redacted. No historic account-wide backfill.
- Persist `tool_calls_json` in both job response and manual reply SQLite rows with migration for older databases. Tool-only SSE before the answer is saved while the accepted lease remains active; repeated and later snapshots merge by invocation ID without losing terminal results. Exact-branch manual reply route normalization keeps the associated tool metadata. UI renders a compact timeline with expandable input/output/error and truthful running/completed/failed states before the final Markdown answer.
- Nox isolated worktree full real-Chromium pytest gate #2308 passed **492 tests** before integrating the newer queued-chat changes. After rebase, #2320 Bun/Svelte/TypeScript/Vite passed, #2321 strict Ty passed, and #2323 full real-Chromium pytest passed **502 tests in 281.59s**. Ruff passed after repairing a single test-function boundary newline; no lint/type rule was relaxed.
- Five real browser sizes (1440×900 desktop; 320×700, 360×800, 390×844, 412×915 mobile) passed direct local-only GET, expandable cards, error styling, final Markdown visibility and horizontal-overflow assertions. #2315 saved owner-only screenshot evidence under `~/.local/state/prompta/tool-call-review-20261029/`; desktop, 320px and 390px captures were opened and visually inspected. Synthetic owned SSE→collector→SQLite→API and manual-reply persistence tests prove end-to-end storage without sending new ChatGPT prompts.
