# Prompta service architecture

Prompta is a jobs-only scheduler and fresh-chat dispatcher. Conversation viewing and result processing are deliberately outside the system.

## Components

| Unit | Owns | Does not own |
| --- | --- | --- |
| prompta-ui.service | Jobs CRUD/status API and jobs-only Svelte UI | Chat history, messages, replies, assistant output |
| prompta-scheduler.service | Due-time calculation and durable job-delivery enqueue | Browser automation or result tracking |
| prompta-delivery-worker.service | Delivery claims, retry policy, fresh-tab prompt submission | Assistant-response polling or conversation persistence |
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
                        submit prompt
                               |
                     confirm acceptance
                               |
                          close tab

The durable queue stores job-delivery metadata only. It does not store conversation IDs, assistant messages, transcripts, attachments, reply targets, or UI chat state.

## Completion rule

A Prompta job run is complete when prompt submission is confirmed. The assistant may continue producing a response on ChatGPT's servers after the Prompta-owned browser tab has been closed; Prompta does not observe that response.

Pre-dispatch failures are retryable. A post-dispatch outcome that cannot be proven is terminal outcome_unknown, preventing an automatic duplicate.

## Legacy migration

On first access to an older delivery database, Prompta copies only legacy queue rows whose operation was once into job_deliveries and drops the old generic send_jobs table. Legacy reply/manual-send rows are intentionally discarded.

## Service control

    systemctl --user restart prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser
    systemctl --user status prompta-ui prompta-scheduler prompta-delivery-worker prompta-browser

There is no prompta-conversation-worker.service.
