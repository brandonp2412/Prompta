# Prompta

Prompta is a scheduled-job dispatcher for ChatGPT. It intentionally does not act as a ChatGPT client.

## Scope

Prompta does four things:

1. Stores scheduled jobs.
2. Enqueues due job runs durably.
3. Opens a fresh ChatGPT chat for each run and submits the job prompt.
4. Closes the Prompta-owned tab as soon as submission is confirmed.

Assistant responses are not read, cached, parsed, rendered, recovered, or reconciled. Prompta does not reply to existing chats, retain conversation IDs, expose a chat history UI, or provide Machine Gun Mode.

## Services

| Service | Responsibility |
| --- | --- |
| prompta-ui.service | Jobs-only web UI and jobs API |
| prompta-scheduler.service | Decides when jobs are due and enqueues one delivery per occurrence |
| prompta-delivery-worker.service | Claims queued deliveries, submits each in a new ChatGPT tab, then closes it |
| prompta-browser.service | Authenticated Chromium instance used only for prompt submission |

The services are grouped by prompta.target. There is no conversation worker.

## Web UI

The web UI exposes only:

- GET / — jobs manager
- GET /api/jobs — configured jobs and scheduler state
- POST /api/jobs — add, edit, pause, resume, remove, or clear jobs
- GET /api/health — service/browser/queue health

There are no chat, transcript, message, reply, attachment, pin, read-state, or result endpoints.

## Delivery semantics

Each scheduled occurrence becomes a durable job_deliveries row. The delivery worker opens a new ChatGPT tab, verifies the composer, enters the scheduled prompt, submits it, confirms only that ChatGPT accepted the submission, and closes the Prompta-owned tab immediately.

The worker never waits for or inspects the assistant response.

If a failure is known to occur before dispatch, the job can be retried. If submission may have happened but Prompta cannot prove the outcome, the delivery is marked outcome_unknown instead of automatically resending and risking a duplicate.

Legacy generic queue rows are migrated only when they represent once/fresh-chat deliveries. Legacy reply rows are discarded.

## Job CLI

    prompta add nightly-review "Review the project and improve it" --daily-at 21:00
    prompta add frequent-check "Run the configured check" --interval-minutes 40
    prompta list
    prompta pause nightly-review
    prompta resume nightly-review
    prompta remove nightly-review
    prompta clear

--exact-interval disables scheduler jitter for interval jobs.

## Development

Python:

    uv sync --locked
    uv run ruff check src tests
    uv run ty check src
    uv run pytest -q

UI:

    bun install --frozen-lockfile
    bun run check

Build the UI with:

    bun run build
