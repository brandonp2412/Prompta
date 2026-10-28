# Prompta service architecture

Prompta is a job-centric scheduler and fresh-chat dispatcher. Its only conversation view is a read-only record of responses passively captured from Prompta-owned job tabs.

## Components

| Unit | Owns | Does not own |
| --- | --- | --- |
| prompta-ui.service | Jobs CRUD/status plus local SQLite-only `/api/results` and read-only Chats view | ChatGPT browser access, account-wide history, replies |
| prompta-scheduler.service | Due-time calculation and durable job-delivery enqueue | Browser automation or result tracking |
| prompta-delivery-worker.service | Delivery claims, due-time fresh-tab submissions, and independent overlapping passive captures into private SQLite | Extra ChatGPT reads, retries after ambiguous sends, historical tab reopening |
| prompta-browser.service | Authenticated Chromium/CDP session | Scheduling or job state |

prompta.target starts these four services. The old conversation worker does not exist.

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

A delivery is accepted when prompt submission is confirmed. Its *response* is completed only with explicit final evidence. After acceptance, each passive capture runs independently; verified answer changes refresh its 45-minute inactivity lease. The independent watchdog closes idle owned tabs, even after worker failure. New chats are dispatched when due without an artificial global send interval; active captures may overlap. Partial/failed captures remain distinct from completed ones. Connector approvals and global rate-limit backoff remain in force.

Pre-dispatch failures are retryable. A post-dispatch outcome that cannot be proven is terminal outcome_unknown, preventing an automatic duplicate.


## Service control

    systemctl --user restart prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser
    systemctl --user status prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser

There is no prompta-conversation-worker.service.
