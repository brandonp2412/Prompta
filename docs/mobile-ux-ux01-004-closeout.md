# UX01-004 — Jobs image picker and action footer

30 October 2026 NZDT. Owner-only visual evidence: `/home/brandon/.local/share/prompta/qa/mobile-ux-20261030/ux01-004/`.

## Predecessor and overlap gate

Read `AGENTS.md`, `docs/prompta-chat-ui-restoration.md`, and the Stage 01 inventory's `stage-evidence.md` and 320×700 screenshot atlas. Stage 01 `84be73a` is already an ancestor of Nox main `a30b51e`. The later integrated `a7e6e5a` already introduced a normal-flow footer for widths up to 420px, correcting the original 320×700 visual order. The Nox main checkout was clean; no running Prompta coding/build workers or queued jobs were found at the initial gate. Other worktrees have unrelated in-progress edits, so this change was isolated in `fix/ux01-image-picker-20261030`. Glass's old Prompta checkout is 130 commits behind and has dated, unrelated uncommitted work; it was not touched.

The Galaxy S25 (SM-S931B) was reachable by ADB, but the current focus was `NotificationShade` with `mDreamingLockscreen=true`. No unlock, wake, or device interaction was attempted. Android keyboard behaviour is tested by real Chromium touch events plus a resized viewport, **not** by an unlocked physical phone.

## Reproducible defect ledger

| ID | Severity | Reproduction and evidence | Resolution |
| --- | --- | --- | --- |
| UX01-004 original | P2 | Stage 01 `after/320x700/03-new-job.png` shows Add images below the overlaid sticky footer at the 700px viewport bottom. An earlier normal-flow experiment failed touch hit testing after keyboard resize and was reverted. | Already corrected by integrated `a7e6e5a` on current main. At 320×700, `before/320x700/03-new-job.png` and `after/320x700/01-new-job.png` in this closeout show Add images **above** the normal-flow actions, with no overlap. |
| UX01-004 desktop regression | P2 | Fresh 1440×900 editor: sticky footer occluded the image picker. `before/1440x900/03-new-job.png` and `before/1440x900/04-new-job-filled.png` show the obstruction; real coordinate hit testing failed in BUILDQ #2736/#2737. | On desktop widths at least 1000px, stop stretching the prompt field to the footer and cap the editable textarea at `min(38dvh, 420px)` (minimum 220px). The footer remains sticky; portrait and landscape rules remain unchanged. Final `after/1440x900/01-new-job.png` shows Add images fully visible and touch/mouse hit testing passes. |

## Regression contract

`tests/test_mobile_ux_image_picker.py` uses isolated SQLite/HTTP fixtures populated with synthetic jobs and local chats. It runs six browser contexts at 320×700, 360×800, 390×844, 412×915, 844×390 and 1440×900. Real `touchscreen.tap(x,y)` is used for all mobile cases, and a coordinate mouse click for desktop; tests inspect `document.elementFromPoint` before every tap. The file chooser must actually open, without uploading anything. For every narrow portrait width, a 430px keyboard-resize viewport and three repeated scroll/picker/Cancel/Keep editing cycles must work, followed by Cancel/Discard and Edit/Cancel. The test verifies that all network requests are GET/HEAD to its own fixture server; it never saves a live job or sends a message.

Privacy-scrubbed captures are in `after/<viewport>/` (new editor, picker, keyboard, discard and edit states) and original synthetic atlas captures in `before/<viewport>/`. Original native-size 320, 360, 390, 412, landscape and desktop captures and the keyboard/desktop before-after pairs were opened and visually inspected, not merely generated.

## Validation and deployment

- Targeted real-coordinate Playwright gate: BUILDQ #2738, **6 passed**.
- Full Ruff: BUILDQ #2744, **pass**.
- Full Ty with the actual Nox virtual environment: BUILDQ #2745, **pass**.
- Full pytest: BUILDQ #2747, **518 passed, 43 skipped**.
- Bun install: BUILDQ #2746, **pass**.
- Bun/Svelte/TypeScript/Vite check: BUILDQ #2848, **pass** with 0 Svelte errors and 0 warnings.
- Follow-up after Chats became the default route: test explicitly opens ?view=jobs. BUILDQ #2830: **6 passed**, #2837 Ruff **pass**, #2838 Ty **pass**, #2839 pytest **526 passed, 43 skipped**, #2848 Bun **pass**. The 32 synthetic screenshots in retest-20261030-1520/ were captured and representative portrait/keyboard/desktop states visually inspected.
- 17:45 final rebased branch on current main `4f6d721` (no CSS/test overlap). BUILDQ #2942 real-touch six-viewport Playwright **6 passed**; #2943 full Ruff check **pass**; #2946 Ty **pass**; #2947 full pytest **551 passed, 43 skipped**; #2951 Bun/Svelte/TypeScript/Vite **pass**, 0 Svelte errors/warnings. BUILDQ #2956 formatted only the new test. Repo-wide `ruff format --check .` reports 49 pre-existing files requiring formatting, unrelated to this fix; no blanket formatting was performed. Generated Vite bundle only changed node_modules path annotations and was restored.
- Inspected actual original and rebased 320×700 normal/keyboard and 1440×900 screenshot PNGs at native resolution: picker above footer and tappable. Hardware Galaxy S25 unlocked but Rotta active in foreground; did not interrupt unrelated app.
- Integration, push, deployed synthetic browser gate and service health: pending final gate.

Only `src/static/app.css`, the targeted regression test and this documentation are intended source changes. Do not change the mobile portrait footer or production job data.
