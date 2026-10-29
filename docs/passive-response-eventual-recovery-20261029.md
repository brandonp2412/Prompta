# Passive response capture recovery (29 Oct 2026)

## Scope

- A transient failure of the original owned-tab response observer no longer immediately ends capture. The capture worker keeps waiting within its existing 45-minute verified-idle TTL.
- Every 45 seconds while that lease is live, the worker reads only the already-installed semantic observer in the same Prompta-owned tab. This can recover a final answer when the Playwright callback was missed. The same bounded pass attempts to bind a late-arriving exact conversation route.
- Recovery does not navigate/reopen a tab, call a ChatGPT GET/history endpoint, re-send an accepted prompt, or splice another answer branch. Completed rows remain immutable and mismatched identities remain rejected by ResponseStore.
- Expired/interrupted records with no saved branch identity cannot be retrospectively recovered under the current no-history/no-revival contract. No result status is presented as completed without final-answer evidence.

## Verification

- New regression: a synthetic observer exception followed by a same-tab semantic final answer is recovered as `completed` under the original lease. The conversation ID is supplied only through the later pathname probe, not the capture payload.
- Existing tests cover disconnect with partial preservation, rate-limit interruption, branch rollover refusal, SSE completion and private SQLite lease behavior.
- `tests/test_passive_results.py`: 14 passed, including a real local Chromium DOM-observer recovery with no nonlocal network requests.
- Full Python suite was queued through `buildq`/pueue task 2128 and succeeded on the isolated worktree before the final annotation-only test edit.
- Full-repository Ruff and strict Ty checks passed after the final test edit.

## Limits and deployment

This improves recoverability for live owned tabs. A chat whose tab already expired and whose conversation ID was never stored cannot be identified by local state alone. Any historical ChatGPT branch-read mechanism would require an explicit change to the current Prompta access contract and additional branch-bound authorization/tests.
