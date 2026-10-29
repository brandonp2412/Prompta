# Historical response recovery

The delivery worker now runs a read-only reconciliation loop for unfinished
Prompta-created chats. It is deliberately separate from prompt submission and
the live passive SSE/DOM capture path.

- Candidates are only local `job_responses` rows with `interrupted` or
  `unavailable` status, no active capture lease, and an already-recorded
  conversation UUID. No account conversation list is read.
- The worker opens the ordinary ChatGPT UI for the exact stored UUID in its own
  short-lived Chromium tab. It validates the URL and first user prompt before
  reading visible assistant-answer markdown. It never clicks Send, writes to the
  composer, or retries an ambiguous message submission.
- One navigation is permitted globally every 90 seconds, persisted in SQLite
  across service restarts. Each unresolved chat backs off independently from
  90 seconds to at most one hour, with retries continuing until completion.
- Detected account rate limiting suspends reads for at least five minutes
  through a durable read-only exponential backoff. Longer server-provided
  `Retry-After` delays are honoured; chat dispatch remains independent. A browser security challenge creates a separate durable
  30-minute account-wide pause; do not attempt to bypass the challenge.
- Partial text may be preserved without marking a response complete. Completion
  requires an explicit rendered Copy action and no active generation indicator.
  A completed row is immutable. The probe does not read reasoning/thought UI or
  store raw SSE frames.
- Browser navigation failures and prompt/branch mismatches leave the original
  run intact and eligible for later retry. Manual intervention may be needed to
  restore an authenticated Chromium session after a security challenge.

The retry state lives in `history_recovery_attempts` alongside the existing
owner-private `chat-results.sqlite3` database. Run
`pytest tests/test_history_recovery.py tests/test_history_probe_browser.py`
and `node tests/historyResponseProbe.test.cjs` to exercise its gates.
