import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createJobsPageController, type Props } from "./JobsPageController";
import JobEditor from "./JobEditor";
import { queueEtaExplanation, queueEtaText } from "./queueStatus";

export default function JobsPage(props: Props) {
  const model = useMemo(() => createJobsPageController(props), []);
  useSignals();
  const {
    deliveryHealth,
    deliveryHealthError,
    jobsLoadError,
    queueSnapshot,
    waitingJob,
    pendingDeliveries,
    recoveryPauseSeconds,
    filterOptions,
    pageSize,
    jobs,
    activeFilters,
    showRepeatingJobs,
    repeatingJobsCount,
    cadenceJobs,
    filteredJobs,
    filterCounts,
    page,
    pageCount,
    visibleJobs,
    allVisiblePaused,
    status,
    saving,
    editorOpen,
    beginNew,
    beginOnce,
    onEditorKeydown,
    formatDate,
    scheduleText,
    toggleFilter,
    jobStateText,
    changePage,
    loadDeliveryHealth,
    load,
    command,
    edit,
    remove,
    toggleVisible,
    clearAll,
  } = model;
  const refs = useMemo(
    () => ({
      jobsTitle: (element: HTMLHeadingElement | null) => {
        if (model.jobsTitle.peek() !== (element ?? undefined))
          model.jobsTitle.value = element ?? undefined;
      },
      editorPage: (element: HTMLElement | null) => {
        if (model.editorPage.peek() !== (element ?? undefined))
          model.editorPage.value = element ?? undefined;
      },
      editorForm: (element: HTMLFormElement | null) => {
        if (model.editorForm.peek() !== (element ?? undefined))
          model.editorForm.value = element ?? undefined;
      },
      nameInput: (element: HTMLInputElement | null) => {
        if (model.nameInput.peek() !== (element ?? undefined))
          model.nameInput.value = element ?? undefined;
      },
      promptInput: (element: HTMLTextAreaElement | null) => {
        if (model.promptInput.peek() !== (element ?? undefined))
          model.promptInput.value = element ?? undefined;
      },
      imageInput: (element: HTMLInputElement | null) => {
        if (model.imageInput.peek() !== (element ?? undefined))
          model.imageInput.value = element ?? undefined;
      },
      imagePreviewList: (element: HTMLDivElement | null) => {
        if (model.imagePreviewList.peek() !== (element ?? undefined))
          model.imagePreviewList.value = element ?? undefined;
      },
      editorFooter: (element: HTMLDivElement | null) => {
        if (model.editorFooter.peek() !== (element ?? undefined))
          model.editorFooter.value = element ?? undefined;
      },
    }),
    [model],
  );
  useLayoutEffect(() => {
    model.syncProps(props);
  });
  useEffect(() => model.mount(), [model]);
  useEffect(() => {
    window.addEventListener("keydown", onEditorKeydown);
    return () => {
      window.removeEventListener("keydown", onEditorKeydown);
    };
  }, [model]);

  function deliveryLabel() {
    if (deliveryHealthError.value) return "status unavailable";
    if (deliveryHealth.value?.ready === false) return "needs attention";
    if (deliveryHealth.value?.admission?.blocked) return "waiting for capacity";
    return deliveryHealth.value ? "online" : "status unavailable";
  }

  return (
    <>
      {!editorOpen.value ? (
        <>
          <section aria-labelledby="jobs-title" className="jobs-panel">
            <div className="jobs-toolbar">
              <div className="toolbar-title">
                <h1 id="jobs-title" ref={refs.jobsTitle}>
                  Jobs
                </h1>
                <span>{cadenceJobs.value.length}</span>
              </div>

              <div className="toolbar-actions">
                <span role="status" aria-live="polite" className="status-line">
                  {status.value}
                </span>

                <button
                  type="button"
                  disabled={!visibleJobs.value.length || saving.value}
                  title={
                    allVisiblePaused.value
                      ? "Resume the jobs shown on this page"
                      : "Pause the jobs shown on this page"
                  }
                  aria-label={allVisiblePaused.value ? "Resume visible jobs" : "Pause visible jobs"}
                  onClick={() => void toggleVisible()}
                  className="toolbar-button visible-toggle"
                >
                  <span className="action-copy">
                    {allVisiblePaused.value ? "Resume visible" : "Pause visible"} (
                    {visibleJobs.value.length})
                  </span>
                  <span aria-hidden="true" className="compact-action-icon">
                    {allVisiblePaused.value ? (
                      <>
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="m8 5 11 7-11 7z"></path>
                        </svg>
                      </>
                    ) : (
                      <>
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M8 5v14M16 5v14"></path>
                        </svg>
                      </>
                    )}
                  </span>
                </button>

                <button
                  type="button"
                  disabled={saving.value}
                  aria-label="Refresh jobs"
                  title="Refresh jobs"
                  onClick={() => void load()}
                  className="toolbar-button refresh-action"
                >
                  <span className="action-copy">Refresh</span>
                  <span aria-hidden="true" className="compact-action-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M20 7v5h-5M4 17v-5h5"></path>
                      <path d="M5.9 9A7 7 0 0 1 18.5 7L20 12M4 12l1.5 5A7 7 0 0 0 18.1 15"></path>
                    </svg>
                  </span>
                </button>
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={beginOnce}
                  className="toolbar-button run-once-action"
                >
                  Run once
                </button>
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={beginNew}
                  className="primary-button"
                >
                  New job
                </button>
              </div>
            </div>

            {jobsLoadError.value ? (
              <>
                <div
                  role="alert"
                  className={["result-error recovery-error jobs-recovery-error"]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <span>{jobsLoadError.value}</span>
                  <button type="button" onClick={() => void load()}>
                    Retry jobs
                  </button>
                </div>
              </>
            ) : (
              <></>
            )}

            {deliveryHealth.value || deliveryHealthError.value ? (
              <>
                <details className="delivery-diagnostics">
                  <summary>
                    <span
                      className={[
                        "delivery-indicator",
                        Boolean(deliveryHealthError.value) ||
                        deliveryHealth.value?.ready === false ||
                        deliveryHealth.value?.admission?.blocked === true
                          ? "degraded"
                          : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    ></span>
                    Delivery {deliveryLabel()}
                    {deliveryHealth.value ? (
                      <>
                        <span className="delivery-count">{pendingDeliveries.value} pending</span>
                        {deliveryHealth.value.queue.outcome_unknown ? (
                          <>
                            <span className="delivery-count">
                              {deliveryHealth.value.queue.outcome_unknown} unconfirmed historically
                            </span>
                          </>
                        ) : (
                          <></>
                        )}
                        {recoveryPauseSeconds.value > 0 &&
                        (deliveryHealth.value.recovery.recoverable > 0 ||
                          deliveryHealth.value.recovery.recoverable_reply_captures > 0) ? (
                          <>
                            <span className="delivery-count">Recovery paused</span>
                          </>
                        ) : (
                          <></>
                        )}
                      </>
                    ) : (
                      <></>
                    )}
                  </summary>
                  {deliveryHealthError.value ? (
                    <>
                      <p role="alert">
                        {deliveryHealthError.value}{" "}
                        <button type="button" onClick={() => void loadDeliveryHealth()}>
                          Retry
                        </button>
                      </p>
                    </>
                  ) : (
                    <></>
                  )}
                  {deliveryHealth.value ? (
                    <>
                      {deliveryHealthError.value ? (
                        <>
                          <p>
                            Counts below are from the last successful check, not current service
                            status.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                      {deliveryHealth.value.issues.length ? (
                        <>
                          <p role="status">{deliveryHealth.value.issues.join(" · ")}</p>
                        </>
                      ) : (
                        <>
                          {!deliveryHealthError.value ? (
                            <>
                              <p>UI, scheduler, delivery worker and browser are responding.</p>
                            </>
                          ) : (
                            <></>
                          )}
                        </>
                      )}
                      {deliveryHealth.value.admission?.blocked ? (
                        <>
                          <p role="status">
                            Dispatch paused:{" "}
                            {deliveryHealth.value.admission?.reason ||
                              "Host resource admission is blocking new sends"}
                            . Queued jobs are retained until capacity returns; no sends are retried
                            after an uncertain outcome.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                      <dl>
                        <div>
                          <dt>Queued</dt>
                          <dd>{deliveryHealth.value.queue.queued}</dd>
                        </div>
                        <div>
                          <dt>Running</dt>
                          <dd>{deliveryHealth.value.queue.running}</dd>
                        </div>
                        <div>
                          <dt>Retrying</dt>
                          <dd>{deliveryHealth.value.queue.retrying}</dd>
                        </div>
                        <div>
                          <dt>Rate limited</dt>
                          <dd>{deliveryHealth.value.queue.rate_limited}</dd>
                        </div>
                        {deliveryHealth.value.queue.next_retry_at_epoch ? (
                          <>
                            <div>
                              <dt>Next queued retry</dt>
                              <dd>{formatDate(deliveryHealth.value.queue.next_retry_at_epoch)}</dd>
                            </div>
                          </>
                        ) : (
                          <></>
                        )}
                        <div>
                          <dt>Dead letters</dt>
                          <dd>{deliveryHealth.value.queue.dead_lettered}</dd>
                        </div>
                        <div>
                          <dt>Unconfirmed sends</dt>
                          <dd>{deliveryHealth.value.queue.outcome_unknown}</dd>
                        </div>
                      </dl>
                      <dl>
                        <div>
                          <dt>Captures in progress</dt>
                          <dd>{deliveryHealth.value.recovery.active_captures}</dd>
                        </div>
                        <div>
                          <dt>Stale capture leases</dt>
                          <dd>{deliveryHealth.value.recovery.stale_capture_leases}</dd>
                        </div>
                        <div>
                          <dt>Chats eligible for read-only recovery</dt>
                          <dd>{deliveryHealth.value.recovery.recoverable}</dd>
                        </div>
                        <div>
                          <dt>Due for recovery probe</dt>
                          <dd>{deliveryHealth.value.recovery.ready_for_read_only_probe}</dd>
                        </div>
                        <div>
                          <dt>Unresolved follow-up captures</dt>
                          <dd>{deliveryHealth.value.recovery.unresolved_reply_captures}</dd>
                        </div>
                        <div>
                          <dt>Follow-ups eligible for recovery</dt>
                          <dd>{deliveryHealth.value.recovery.recoverable_reply_captures}</dd>
                        </div>
                        <div>
                          <dt>Due follow-up probes</dt>
                          <dd>{deliveryHealth.value.recovery.due_reply_recovery_probes}</dd>
                        </div>
                        <div>
                          <dt>Missing verified chat identity</dt>
                          <dd>{deliveryHealth.value.recovery.missing_verified_identity}</dd>
                        </div>
                      </dl>
                      {deliveryHealth.value.recovery.stale_capture_leases > 0 ? (
                        <>
                          <p role="status">
                            A capture lease is overdue. The worker will reconcile it as interrupted
                            before read-only recovery; the original send is never replayed.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                      {recoveryPauseSeconds.value > 0 &&
                      (deliveryHealth.value.recovery.recoverable > 0 ||
                        deliveryHealth.value.recovery.recoverable_reply_captures > 0) ? (
                        <>
                          <p role="status">
                            Read-only recovery is waiting for the account safety cooldown (about{" "}
                            {Math.ceil(recoveryPauseSeconds.value / 60)} min). No automatic resends
                            will occur.
                          </p>
                        </>
                      ) : (
                        <>
                          {deliveryHealth.value.recovery.global_pace_seconds > 0 &&
                          deliveryHealth.value.recovery.ready_for_read_only_probe > 0 ? (
                            <>
                              <p>
                                Read-only recovery is paced to one verified chat at a time; next
                                probe in about{" "}
                                {Math.ceil(deliveryHealth.value.recovery.global_pace_seconds)}{" "}
                                seconds.
                              </p>
                            </>
                          ) : (
                            <></>
                          )}
                        </>
                      )}
                      {deliveryHealth.value.recovery.missing_verified_identity > 0 ? (
                        <>
                          <p>
                            Chats without a verified conversation identity cannot be recovered
                            automatically. Their local partial results remain available.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                      {deliveryHealth.value.queue.retrying ||
                      deliveryHealth.value.queue.rate_limited ? (
                        <>
                          <p>
                            Rejected or pre-dispatch attempts retry automatically after their
                            backoff.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                      {deliveryHealth.value.queue.outcome_unknown ? (
                        <>
                          <p>
                            Unconfirmed sends are not automatically retried. Review the exact saved
                            chat before sending again.
                          </p>
                        </>
                      ) : (
                        <></>
                      )}
                    </>
                  ) : (
                    <></>
                  )}
                </details>
              </>
            ) : (
              <></>
            )}

            <div role="group" aria-label="Filter jobs" className="jobs-summary">
              {filterOptions.map((option, __index) => (
                <React.Fragment key={option.key}>
                  <button
                    type="button"
                    aria-pressed={activeFilters.value[option.key]}
                    title={option.title}
                    onClick={() => toggleFilter(option.key)}
                    className={["filter-chip", activeFilters.value[option.key] ? "chosen" : ""]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {option.label} <span>{filterCounts.value[option.key]}</span>
                  </button>
                </React.Fragment>
              ))}
              <button
                type="button"
                aria-pressed={showRepeatingJobs.value}
                title="Include daily and interval-based repeating jobs"
                onClick={() => {
                  showRepeatingJobs.value = !showRepeatingJobs.value;
                  page.value = 1;
                }}
                className={["filter-chip", showRepeatingJobs.value ? "chosen" : ""]
                  .filter(Boolean)
                  .join(" ")}
              >
                Repeating jobs <span>{repeatingJobsCount.value}</span>
              </button>
            </div>

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

              {filteredJobs.value.length === 0 ? (
                <>
                  <div className="empty-row">
                    {jobs.value.length ? "No jobs match these filters." : "No scheduled jobs."}
                  </div>
                </>
              ) : (
                <></>
              )}

              {visibleJobs.value.map((job, __index) => (
                <React.Fragment key={job.name}>
                  <div role="row" className="job-row">
                    <div role="cell" className="job-main">
                      <div className="job-name">{job.name}</div>
                      <div title={job.prompt} className="job-prompt">
                        {job.prompt}
                      </div>
                      {job.images?.length ? (
                        <>
                          <div className="job-image-count">
                            {job.images.length} image{job.images.length === 1 ? "" : "s"}
                          </div>
                        </>
                      ) : (
                        <></>
                      )}
                      <div className="job-submeta">
                        <span>Last sent {formatDate(job.last_sent_at)}</span>
                        {job.source_revision ? (
                          <>
                            <span title={job.source_revision}>
                              rev {job.source_revision.slice(0, 8)}
                            </span>
                          </>
                        ) : (
                          <></>
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
                      <span
                        className={["state-value", job.status === "failing" ? "error" : ""]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <span className="state-dot"></span>
                        {jobStateText(job)}
                      </span>
                      {waitingJob(job.name) && queueSnapshot.value ? (
                        <span
                          className="job-queue-eta"
                          role="status"
                          title={queueEtaExplanation(queueSnapshot.value)}
                        >
                          Queue #{waitingJob(job.name)!.position} of{" "}
                          {queueSnapshot.value.waiting.length}
                          {" · "}
                          {queueEtaText(waitingJob(job.name)!)}
                        </span>
                      ) : null}
                      {job.status_message ? (
                        <>
                          <span className="job-message">{job.status_message}</span>
                        </>
                      ) : (
                        <></>
                      )}
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
                      {!job.run_at_epoch ? (
                        <>
                          <button
                            type="button"
                            disabled={saving.value}
                            onClick={() => edit(job)}
                            className="row-action"
                          >
                            Edit
                          </button>
                        </>
                      ) : (
                        <></>
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
                </React.Fragment>
              ))}
            </div>

            {filteredJobs.value.length > pageSize ? (
              <>
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
              </>
            ) : (
              <></>
            )}

            {jobs.value.length ? (
              <>
                <footer className="jobs-footer">
                  <button
                    type="button"
                    disabled={saving.value}
                    onClick={() => void clearAll()}
                    className="row-action danger-text"
                  >
                    Clear all jobs
                  </button>
                </footer>
              </>
            ) : (
              <></>
            )}
          </section>
        </>
      ) : (
        <></>
      )}

      {editorOpen.value && <JobEditor model={model} refs={refs} />}
    </>
  );
}
