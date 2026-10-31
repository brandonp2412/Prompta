import { useSignals } from "@preact/signals-react/runtime";
import type { createJobsPageController } from "./JobsPageController";
import { queueEtaExplanation, queueEtaText } from "./queueStatus";

type Controller = ReturnType<typeof createJobsPageController>;

export default function JobsTable({ model }: { model: Controller }) {
  useSignals();
  const {
    jobs,
    filteredJobs,
    visibleJobs,
    formatDate,
    scheduleText,
    jobStateText,
    waitingJob,
    queueSnapshot,
    saving,
    command,
    edit,
    remove,
    pageSize,
    page,
    pageCount,
    changePage,
  } = model;

  return (
    <>
      <div role="table" aria-label="Scheduled jobs" className="jobs-table">
        <div role="row" className="jobs-table-head">
          <span role="columnheader">Job</span>
          <span role="columnheader">Schedule</span>
          <span role="columnheader">Next run</span>
          <span role="columnheader">State</span>
          <span role="columnheader" className="actions-heading">
            Actions
          </span>
        </div>

        {filteredJobs.value.length === 0 && (
          <div className="empty-row">
            {jobs.value.length ? "No jobs match these filters." : "No scheduled jobs."}
          </div>
        )}

        {visibleJobs.value.map((job) => {
          const waiting = waitingJob(job.name);
          return (
            <div key={job.name} role="row" className="job-row">
              <div role="cell" className="job-main">
                <div className="job-name">{job.name}</div>
                <div title={job.prompt} className="job-prompt">
                  {job.prompt}
                </div>
                {job.images.length > 0 && (
                  <div className="job-image-count">
                    {job.images.length} image{job.images.length === 1 ? "" : "s"}
                  </div>
                )}
                <div className="job-submeta">
                  <span>Last sent {formatDate(job.last_sent_at)}</span>
                  {job.source_revision && (
                    <span title={job.source_revision}>rev {job.source_revision.slice(0, 8)}</span>
                  )}
                </div>
              </div>

              <div role="cell" className="job-cell schedule-cell">
                <span className="cell-label">Schedule</span>
                <span>{scheduleText(job)}</span>
              </div>

              <div role="cell" className="job-cell">
                <span className="cell-label">Next run</span>
                <span>{job.paused ? "Paused" : formatDate(job.next_due_at_epoch)}</span>
              </div>

              <div role="cell" className="job-cell state-cell">
                <span className="cell-label">State</span>
                <span className={job.status === "failing" ? "state-value error" : "state-value"}>
                  <span className="state-dot"></span>
                  {jobStateText(job)}
                </span>
                {waiting && queueSnapshot.value && (
                  <span
                    className="job-queue-eta"
                    role="status"
                    title={queueEtaExplanation(queueSnapshot.value)}
                  >
                    Queue #{waiting.position} of {queueSnapshot.value.waiting.length}
                    {" · "}
                    {queueEtaText(waiting)}
                  </span>
                )}
                {job.status_message && <span className="job-message">{job.status_message}</span>}
              </div>

              <div role="cell" className="job-actions">
                <button
                  type="button"
                  disabled={saving.value}
                  title={
                    job.daily_at || job.run_at_epoch
                      ? "Launch a fresh chat without moving the fixed schedule"
                      : "Launch a fresh chat and restart the interval countdown"
                  }
                  onClick={() =>
                    void command(
                      { action: "fire_now", name: job.name },
                      "Queued one fresh chat for " + job.name + ".",
                      {
                        prompt: job.prompt,
                        images: job.images.map((image) => image.ref),
                        scope: "jobs:fire:" + job.name + ":" + job.pin_chat,
                      },
                    )
                  }
                  className="row-action"
                >
                  Fire now
                </button>
                {!job.run_at_epoch && (
                  <button
                    type="button"
                    disabled={saving.value}
                    onClick={() => edit(job)}
                    className="row-action"
                  >
                    Edit
                  </button>
                )}
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={() =>
                    void command(
                      { action: job.paused ? "resume" : "pause", name: job.name },
                      (job.paused ? "Resumed " : "Paused ") + job.name + ".",
                    )
                  }
                  className="row-action"
                >
                  {job.paused ? "Resume" : "Pause"}
                </button>
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={() => void remove(job)}
                  className="row-action danger-text"
                >
                  Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {filteredJobs.value.length > pageSize && (
        <nav aria-label="Job pages" className="pagination">
          <span>
            Page {page.value} of {pageCount.value}
          </span>
          <div className="pagination-actions">
            <button
              type="button"
              disabled={page.value <= 1}
              onClick={() => changePage(page.value - 1)}
              className="toolbar-button"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page.value >= pageCount.value}
              onClick={() => changePage(page.value + 1)}
              className="toolbar-button"
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </>
  );
}
