# Prompta Mobile UX Repair — Stage 01 Inventory Evidence

Date: 29 October 2026 (Pacific/Auckland). Baseline main: a817bf6. Repair worktree: /home/brandon/.worktrees/prompta-mobile-ux-01-inventory-20261029, branch fix/mobile-ux-01-inventory-20261029.

## Safety and test method

- Read /home/brandon/prompta/AGENTS.md and docs/prompta-chat-ui-restoration.md before changes. Main and origin/main matched at baseline; the preceding mobile worktree was already integrated. An unrelated active night-concurrency worker was editing backend delivery/scheduler files, with no UI file overlap. Recheck before integration.
- Real headless Chromium Playwright with touch/mobile emulation at **320×700**, **360×800**, **390×844**, **412×915**, **844×390 landscape**, and desktop **1440×900**. This is browser emulation, not hardware.
- Temporary isolated SQLite fixture server per test; 16 synthetic Jobs, five synthetic local Chats, completed two-turn branch, queued and partial states, long markdown/code, search, pinning and empty/error responses. No live messages dispatched. The browsing atlas only uses GET/HEAD; the named one-time-save test modifies its own fixture database.
- Opened and visually reviewed at original resolution all **69 first-pass review sheets**, then the changed final after-sheets of the **71-sheet / 234-screenshot** atlas plus native-size phone, landscape and desktop captures. Checked wrapping, touch target sizes, overlay intersections, scroll, keyboard simulation, sidebar, composer and error text. Re-review changed captures before acceptance.
- A Galaxy S25 SM-S931B was connected over ADB but asleep behind the lock screen. No unlock/bypass was attempted; its sleep state was restored and the temporary reverse port removed. Hardware visual check unavailable; the unusable black capture is not a pass.

## Prioritized reproducible defect ledger

| ID | Priority | Reproduction / baseline observation | Outcome | Evidence |
|---|---|---|---|---|
| UX01-001 | **P1** | At 360×800/390×844, tap **New job**: editor says **Run once**, lacks Name field and offers immediate Run once. | Fixed root cause: reset defaults to interval, and one-off action derives from explicit new=once route. Switching New job schedule to Once retains Name/Create job. | before/390x844/03-new-job.png vs after/390x844/03-new-job.png and 03b-named-one-time-job.png |
| UX01-002 | **P1** | At 844×390, fill job prompt: sticky footer bisects textarea and obscures text; toolbar has cramped/wrapped actions. | Fixed landscape-only layout: 210px sidebar, wrapped toolbar, static footer below textarea; E2E asserts footer top is below textarea bottom and scrolls to actions. | before/844x390/04-new-job-filled.png vs after/844x390/04-new-job-filled.png and 04b-landscape-actions.png |
| UX01-003 | **P2** | Undersized targets: Edit 37×44px, Add images 89×32, transcript Copy 45×27, Copy code 74×30, composer Attach 34×34, Send 36×36. | Shared CSS gives main Jobs, Chats, transcript, pin, refresh, pagination, composer controls at least 44px targets; E2E measures composer targets. | before/*/measurements.txt vs after/*/measurements.txt |
| UX01-004 | **P2 open** | On fresh 320×700 job editor, sticky action bar initially sits above Add images row at screen bottom. Picker requires scroll and visual order is confusing. | A static portrait footer was tried, but real touch hit testing failed after keyboard emulation (tap landed on footer background). Reverted. Needs targeted design+hardware retest. | after/320x700/03-new-job.png and failed test screenshots under attempts/ |
| UX01-005 | **P3** | Svelte warns ChatsPage scrollPane and JobsPage imageInput were assigned without reactive declaration. | Both changed to state declarations; later Svelte check reports 0 errors, 0 warnings. | BUILDQ #1878 and final frontend check |
| UX01-006 | **P3 observed, no fix** | Empty Chats, no matches, empty Jobs, and injected 503 jobs/local results error states have readable distinct messages at 390 and desktop, without clipping in reviewed frames. | No change required. | before and after 390x844 and 1440x900 empty/error screenshots |

## Interaction coverage

Jobs list and scrolling/pagination, status chips, row action affordances, new recurring job, named Once selection, Run once route, edit form, unsaved-change/Discard confirmation, phone drawer; Chats list, refresh, filtering, pin, empty search, thread top/bottom, second-turn branch, Markdown/code, collapsed/expanded long prompts, exact-branch reply draft, fresh composer and synthetic keyboard. Native Remove and Clear-all confirmations dismissed in isolated fixtures. No Fire now, Send or unrelated live job action.

## Validation / integration ledger

- Baseline atlas BUILDQ #1858, #1860, #1861, #1863, #1866.
- Passing 6-viewport browser atlas #1879, #1909 (8 tests).
- Ruff #1875 pass; Ty #1881 pass with actual Nox virtualenv and strict-editable package path (no disabled rules); Bun TS/Svelte/Vite #1878/#1893 pass (0 Svelte warnings); full pytest #1882/#1888 413 passed before two later fixture tests.
- Additional isolated named one-time-save and destructive-confirmation tests **BUILDQ #1910: 10 passed**. Final branch validation: Ruff #1911 pass; Ty #1912 pass; pytest #1913 **404 passed, 11 skipped**; Bun/Svelte/TypeScript/Vite #1914 pass, 0 Svelte warnings; final navigable atlas #1915 pass.
- UI/static/E2E code only. No delivery/scheduler/branch/TTL code modified.
- Main advanced to 8bf13cc with backend concurrency changes and no overlapping UI paths. Deployment evidence and service health are kept in the private stage evidence log alongside screenshots.

## Follow-up handoff (UX01-004)

At 320×700, the Add images row visually begins below the sticky footer on editor entry. The proposed portrait static footer changed scroll and focus behavior and failed real touchscreen tap hit-testing after visual viewport shrank for a keyboard (tap over Cancel landed on footer background); it was reverted. Preserve the working sticky portrait footer until a revised layout is validated with actual taps at 320, 360, 390, 412, keyboard focus/resize, repeated scroll and edit/back states, plus Galaxy S25 when unlocked. Reuse isolated fixtures and the existing browser atlas. Do not send live messages.

## UX01-004 follow-up closure — 30 October 2026

The original P2 `UX01-004` entry above describes the 29 October inventory state, **not the current state**. The 320×700 Add images/footer overlap was subsequently corrected in ancestor `a7e6e5a`. A remaining desktop picker obstruction was corrected in `src/static/app.css` by `e32e1dd`, with portrait/landscape footer rules preserved. See `docs/mobile-ux-ux01-004-closeout.md` for the precise defect ledger and owner-only screenshot locations.

The six-viewport real-coordinate Playwright gate passed against both isolated local fixtures (BUILDQ #2942, #2959) and deployed Nox static assets with synthetic API fixtures (BUILDQ #2963). Full Ruff, Ty, pytest (551 passed, 43 skipped), Bun/Svelte/Vite passed after rebase; all five relevant systemd services were active, `/api/health` HTTP 200, and served CSS matched deployed main byte-for-byte. Main was pushed with final closeout at `5cc2413`. Physical Galaxy S25 validation was skipped because Rotta was foreground; no user app was interrupted. **UX01-004 closed.**
