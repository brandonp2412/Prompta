# Prompta service architecture

Prompta is a job-centric scheduler and fresh-chat dispatcher. Its only conversation view is a read-only record of responses passively captured from Prompta-owned job tabs.

## Components

| Unit | Owns | Does not own |
| --- | --- | --- |
| prompta-ui.service | Jobs CRUD/status plus local SQLite-only `/api/results` and read-only Chats view | ChatGPT browser access, account-wide history, replies |
| prompta-scheduler.service | Due-time calculation and durable job-delivery enqueue | Browser automation or result tracking |
| prompta-delivery-worker.service | Fresh-chat delivery, independent passive captures, and paced read-only recovery of exact verified conversations | Account-wide history enumeration, internal history API requests, or retries after ambiguous sends |
| prompta-browser.service | Authenticated Chromium/CDP session | Scheduling or job state |
| prompta-connector-approval-watch.service | Opt-in scan of unread ChatGPT sidebar markers, temporary background approval tabs, and permission-only checks in already-open non-Prompta chats | Chat bodies, history APIs, prompt submission, or navigation/closure of user tabs |

prompta.target starts these services. The old conversation worker does not exist.

Connector approval supervision uses the same scoped `approve_connector.js` matcher and `supervise_connector_approvals` loop in both paths. Live delivery/manual-reply capture tabs are primary and check every 200 ms while they own the exact conversation. The independent opt-in service is a slower, one-second-per-tab backup for rendered unread chats from anywhere in the authenticated account, including conversations outside Prompta. It also watches scoped permission controls in already-open non-Prompta ChatGPT tabs, which handles repeated prompts after a chat becomes read. All browser navigations and sidebar refreshes run through SchedulerRuntime's persisted account-wide read backoff; the watcher records ChatGPT HTTP 429 status and Retry-After without reading response bodies. A conversation-load error is not misreported as a completed permission check. Already-open tab DOM permission checks continue locally during read cooldown. It never sends messages or navigates/closes existing user tabs.

## Data flow

    jobs configuration
          |
          v
    scheduler state ----> job_deliveries queue
                               |
                               v
                        delivery worker
                               |
                               v
                    fresh ChatGPT tab
                               |
                        submit fresh prompt
                               |
                     confirm acceptance
                               |
                  passive POST/DOM capture
                          |
                 private chat-results SQLite
                          |
               read-only local Chats UI

The durable queue stores delivery metadata. A separate private per-run response store holds only Prompta-issued prompts and user-facing assistant output, with status and branch identity. There are no attachments, reply targets, or account-wide transcripts.

## Completion rule

A delivery is accepted when prompt submission is confirmed. Its *response* is completed only with explicit final evidence. After acceptance, each passive capture runs independently; verified answer changes refresh its 45-minute inactivity lease. The independent watchdog closes idle owned tabs, even after worker failure. New chats are dispatched when due without an artificial global send interval; active captures may overlap. Partial/failed captures remain distinct from completed ones. Connector approvals remain in force. Read-side throttling never gates new-chat dispatch.

Pre-dispatch failures are retryable. A post-dispatch outcome that cannot be proven is terminal outcome_unknown, preventing an automatic duplicate.


## Read-side rate limits

A `429 Too Many Requests` observed during response capture or exact-conversation historical recovery records a durable, SQLite-backed `read_rate_limit_backoff` independent of delivery admission. Active semantic-DOM recovery probes and historical read navigation pause during this cooldown; already-arriving passive POST/DOM events remain eligible for capture. An accepted prompt is never automatically resent to recover its response, and the cooldown never authorizes history requests or account-wide polling.

The read cooldown starts at five minutes, doubles for repeated rate limits up to a 30-minute exponential cap, adds positive jitter, and honours a longer `Retry-After` (seconds, HTTP date or supported millisecond header). A completed capture after expiry clears the stale backoff. Historical recovery retains its independent 90-second global pacing and per-chat retry state. New scheduled chats and explicit manual replies are not blocked by read-only throttling; a rejected send is retried only as its own bounded queue item, still subject to delivery parallelism. Current cooldown details are available via `SchedulerRuntime.read_admission_status()`.

## Service control

    systemctl --user restart prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser
    systemctl --user status prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser

There is no prompta-conversation-worker.service.


## Manual reply recovery

An interrupted or unavailable passive response capture is not evidence that its ChatGPT
conversation has disappeared. Explicit user Send can continue a saved conversation from
the latest verified assistant message, even if that answer was partial or interrupted.
If the latest response message ID is absent, an explicitly reopened owned conversation
is checked read-only for the exact route, message ordering, saved text and unique parent.
A failed verification leaves the draft available for another Send attempt, and offers a
separate user-triggered contextual fresh-chat fallback.

If no conversation ID was ever captured, an explicit Send creates a new chat containing
the locally saved conversation transcript and user's new message. Original attached
images are included again when available. A repeated uncertain local queue receipt uses
the same request ID; ambiguous ChatGPT POSTs are not automatically resent. Browsing the
local Chats UI still never opens ChatGPT or reads account-wide history.
