# Explicit manual replies — live E2E evidence (29 Oct 2026 NZDT)

## Contract

A user-triggered reply targets only one persisted Prompta conversation and the last
verified assistant parent. Scheduled jobs always create fresh chats. Browsing the
local Chats UI never contacts ChatGPT. No failed or ambiguous reply is resent
automatically.

For older completed runs with a known conversation URL but no saved assistant
message ID, the **Reply to this chat** button explicitly navigates to that exact
branch. Recovery requires one original user turn, one assistant turn, a matching
visible answer, and one distinct UUID (repeated identical IDs are permitted).
It persists the verified parent before revealing the composer. Missing conversation
URLs, competing message IDs, changed text, or externally continued branches are
refused without speculation.

After a verified conversation POST acknowledgment, the manual dispatcher accepts
either an identity-complete SSE result or one new, identity-bound final answer
observed in the already-owned tab. DOM-only capture records an unknown response
parent rather than inventing that backend relationship. The next user reply still
uses the captured assistant ID as its exact parent.

## Actual provider and UI proof

- Nox headless Chromium opened the real local Svelte UI on a temporary isolated
  HTTP port, with the live private SQLite store and the authenticated dedicated
  ChatGPT CDP browser. No mocked ChatGPT provider was used.
- The UI submitted one fresh chat (HTTP 202). Its captured final answer was
  **FIRST**.
- A user click recovered the original branch identity (HTTP 200), then the
  UI composer submitted one reply (HTTP 202); the persisted final answer was
  **SECOND**, status `completed`.
- The same conversation's newly visible composer submitted a second explicit
  follow-up (HTTP 202); the persisted final answer was **THIRD**, status
  `completed`.
- Local `GET /api/results/{send_id}/turns` returned three completed turns,
  all bound to one conversation ID. Each reply's saved `parent_id` exactly
  matched the previous assistant `message_id`.
- Actual browser UI checks at 1440×900 and 390×844 showed two user/assistant
  pairs after the first follow-up, the exact SECOND text, the next reply composer
  and no horizontal overflow. Private, sidebar-masked screenshots are under
  `~/.local/state/prompta/visual-baselines/reply-e2e-20261029/` on Nox.
- An earlier diagnostic reply did reach ChatGPT and return VERIFIED, but its
  original dispatcher remained `dispatching` because it ignored a complete DOM
  observation. This was not resent; it motivated the final capture fix.

## Regression gates

- Full pytest buildq #2130: **435 passed, 19 skipped**.
- Real-Chromium branch/capture/dispatch suite buildq #2134:
  **37 passed**.
- Full Ruff #2131 and strict Ty #2132: pass.
- Bun formatting, Oxlint, strict TypeScript, Svelte and Vite #2133:
  pass; zero Svelte diagnostics.
- Direct live proof additionally checked fresh UI submission, explicit recovery,
  both follow-up POSTs, terminal response storage and exact parent continuity.

## Release handling

The delivery worker caches browser scripts in-process. Install the new package
and restart the UI for reply handling; restart the delivery worker only after
its active owned captures terminate, preserving their leases and responses.
Until it restarts, new runs created by that older worker may require the explicit
per-chat recovery action above. Never interrupt active captures just to apply
the script change.

## Production closeout — 29 Oct 2026 NZDT

- The manual-reply browser now waits for exact-parent DOM hydration before the
  irreversible claim, and can reuse only an identical prepared draft on a new
  explicit click. Transient CDP startup errors receive one bounded **pre-claim**
  connection retry; a claimed/accepted message is never resent. Commits
  `6b3c68f`, `fdcf3e5`, and `b013dd7` are on pushed `main`.
- The production UI's systemd sandbox had `ProtectHome=read-only` while Playwright
  inherited `TMPDIR=/home/brandon/.cache/tmp`, producing `EROFS` during
  `BrowserType.connect_over_cdp` artifact-directory creation. A sandbox clone
  proved authentication worked with the writable state directory. The Nox user
  drop-in `prompta-ui.service.d/30-disk-backed-temp.conf` now sets
  `TMPDIR=/home/brandon/.local/state/prompta/tmp`; daemon reload and UI restart
  succeeded without interrupting any claimed reply.
- Actual authenticated ChatGPT, through the served production Svelte UI, accepted
  exactly one explicit POST (`202`) for the surviving prepared test intent. SQLite
  advanced `prepared → dispatching → completed` and captured the exact expected
  **FOURTH** result with a new assistant message ID. This extended the earlier
  **FIRST → SECOND → THIRD** proof to four completed turns on one conversation,
  with each saved reply parent matching the preceding assistant message ID.
- Fresh real Chromium reloads at **1440×900** and **390×844** displayed all four
  answers and the current reply composer. Both had no horizontal overflow,
  **zero POSTs** and **zero foreign hosts** during local read-only viewing.
  `/api/health` was OK, browser reachable, and every service heartbeat fresh.
- The 460-test full Python suite, Ruff, strict Ty and Bun/Svelte/Vite passed
  earlier in this recovery; the final connection-retry branch passed **22**
  focused Python/real-Chromium tests plus Ruff and strict Ty. No account-wide
  ChatGPT history was read or imported, and no ambiguous send was retried.
