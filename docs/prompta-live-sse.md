# Prompta local UI live updates

The Jobs and Chats views subscribe to one same-origin EventSource connection
at /api/events. It replaces the old 5-second Jobs and 15-second Chats loops.

- sync: on every connection, including reconnects, invalidate both local
  views. This guarantees recovery if the browser disconnected between database
  commits; Last-Event-ID is not used to replay private records.
- jobs: refresh the Jobs listing after its actual serialized job data changes.
  Health heartbeats in the shared scheduler SQLite database are suppressed
  by a BLAKE2 digest comparison.
- chats: refresh local results, pinned summaries and any selected run after the
  response/reply or outbound queue SQLite database changes.
- Every frame has an SSE id but no private job names, prompts, assistant text,
  branch identifiers, or tool content. All data comes from existing same-origin
  local GET endpoints. No ChatGPT history is read.
- The stream uses HTTP/1.1 chunking, no-cache/no-transform, proxy buffering
  suppression, automatic EventSource reconnect and 15-second comment heartbeats.
- On unsupported/offline streams, a visible tab refreshes every 60 seconds.
  Returning to a visible tab also refreshes. When components unmount, listeners
  detach and the shared source closes.

Detection uses inode, size and mtime-nanoseconds of SQLite databases and WAL
sidecars. It notices writes by the scheduler, capture worker and manual queue
across separate processes without introducing new database write paths or
endangering exactly-once submission. Existing UI generation guards prevent
stale reads from overwriting newer state. Jobs coalesces an update arriving
during an in-flight read.

Historical reference: Prompta's earlier /api/events in db709ee and follow-up
disconnect hardening in be3c9e5. This adapts the concept to the current
job-centric SQLite results architecture without restoring old account-wide
conversation behavior.

Verification: tests/test_live_events.py covers streaming, private-payload
exclusion, Jobs/Chats/queue invalidations, HEAD and reconnects. It also runs
real headless Chromium against an isolated local server to show a new job/chat
without manual refresh and prove idle Jobs no longer polls every five seconds.
