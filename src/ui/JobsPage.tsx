import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createJobsPageController, type Props } from "./JobsPageController";

export default function JobsPage(props: Props) {
  const model = useMemo(() => createJobsPageController(props), []);
  useSignals();
  const {
    deliveryHealth,
    deliveryHealthError,
    jobsLoadError,
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
    editing,
    name,
    prompt,
    images,
    uploadingImage,
    imageInput,
    schedule,
    interval,
    onceDelay,
    pinChat,
    dailyAt,
    exact,
    editorOpen,
    editorError,
    confirmDiscard,
    dirty,
    runOnce,
    duplicateName,
    keepFocusedPromptVisible,
    requestClose,
    discardEditor,
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
    addImages,
    submit,
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

  return (
    <>
      {!editorOpen.value ? (
        <>
          <section
            aria-labelledby="jobs-title"
            className={["jobs-panel"].filter(Boolean).join(" ")}
          >
            <div className={["jobs-toolbar"].filter(Boolean).join(" ")}>
              <div className={["toolbar-title"].filter(Boolean).join(" ")}>
                <h1 id="jobs-title" ref={refs.jobsTitle}>
                  Jobs
                </h1>
                <span>{cadenceJobs.value.length}</span>
              </div>

              <div className={["toolbar-actions"].filter(Boolean).join(" ")}>
                <span
                  role="status"
                  aria-live="polite"
                  className={["status-line"].filter(Boolean).join(" ")}
                >
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
                  className={["toolbar-button visible-toggle"].filter(Boolean).join(" ")}
                >
                  <span className={["action-copy"].filter(Boolean).join(" ")}>
                    {allVisiblePaused.value ? "Resume visible" : "Pause visible"} (
                    {visibleJobs.value.length})
                  </span>
                  <span
                    aria-hidden="true"
                    className={["compact-action-icon"].filter(Boolean).join(" ")}
                  >
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
                  className={["toolbar-button refresh-action"].filter(Boolean).join(" ")}
                >
                  <span className={["action-copy"].filter(Boolean).join(" ")}>Refresh</span>
                  <span
                    aria-hidden="true"
                    className={["compact-action-icon"].filter(Boolean).join(" ")}
                  >
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
                  className={["toolbar-button run-once-action"].filter(Boolean).join(" ")}
                >
                  Run once
                </button>
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={beginNew}
                  className={["primary-button"].filter(Boolean).join(" ")}
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
                <details className={["delivery-diagnostics"].filter(Boolean).join(" ")}>
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
                    Delivery{" "}
                    {deliveryHealthError.value
                      ? "status unavailable"
                      : deliveryHealth.value?.ready === false
                        ? "needs attention"
                        : deliveryHealth.value?.admission?.blocked
                          ? "waiting for capacity"
                          : deliveryHealth.value
                            ? "online"
                            : "status unavailable"}
                    {deliveryHealth.value ? (
                      <>
                        <span className={["delivery-count"].filter(Boolean).join(" ")}>
                          {pendingDeliveries.value} pending
                        </span>
                        {deliveryHealth.value.queue.outcome_unknown ? (
                          <>
                            <span className={["delivery-count"].filter(Boolean).join(" ")}>
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
                            <span className={["delivery-count"].filter(Boolean).join(" ")}>
                              Recovery paused
                            </span>
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

            <div
              role="group"
              aria-label="Filter jobs"
              className={["jobs-summary"].filter(Boolean).join(" ")}
            >
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

            <div
              role="table"
              aria-label="Scheduled jobs"
              className={["jobs-table"].filter(Boolean).join(" ")}
            >
              <div role="row" className={["jobs-table-head"].filter(Boolean).join(" ")}>
                <span role="columnheader">Job</span>
                <span role="columnheader">Schedule</span>
                <span role="columnheader">Next run</span>
                <span role="columnheader">State</span>
                <span role="columnheader" className={["actions-heading"].filter(Boolean).join(" ")}>
                  Actions
                </span>
              </div>

              {filteredJobs.value.length === 0 ? (
                <>
                  <div className={["empty-row"].filter(Boolean).join(" ")}>
                    {jobs.value.length ? "No jobs match these filters." : "No scheduled jobs."}
                  </div>
                </>
              ) : (
                <></>
              )}

              {visibleJobs.value.map((job, __index) => (
                <React.Fragment key={job.name}>
                  <div role="row" className={["job-row"].filter(Boolean).join(" ")}>
                    <div role="cell" className={["job-main"].filter(Boolean).join(" ")}>
                      <div className={["job-name"].filter(Boolean).join(" ")}>{job.name}</div>
                      <div title={job.prompt} className={["job-prompt"].filter(Boolean).join(" ")}>
                        {job.prompt}
                      </div>
                      {job.images?.length ? (
                        <>
                          <div className={["job-image-count"].filter(Boolean).join(" ")}>
                            {job.images.length} image{job.images.length === 1 ? "" : "s"}
                          </div>
                        </>
                      ) : (
                        <></>
                      )}
                      <div className={["job-submeta"].filter(Boolean).join(" ")}>
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

                    <div
                      role="cell"
                      className={["job-cell schedule-cell"].filter(Boolean).join(" ")}
                    >
                      <span className={["cell-label"].filter(Boolean).join(" ")}>Schedule</span>
                      <span>{scheduleText(job)}</span>
                    </div>

                    <div role="cell" className={["job-cell"].filter(Boolean).join(" ")}>
                      <span className={["cell-label"].filter(Boolean).join(" ")}>Next run</span>
                      <span>{job.paused ? "Paused" : formatDate(job.next_due_at_epoch)}</span>
                    </div>

                    <div role="cell" className={["job-cell state-cell"].filter(Boolean).join(" ")}>
                      <span className={["cell-label"].filter(Boolean).join(" ")}>State</span>
                      <span
                        className={["state-value", job.status === "failing" ? "error" : ""]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <span className={["state-dot"].filter(Boolean).join(" ")}></span>
                        {jobStateText(job)}
                      </span>
                      {job.status_message ? (
                        <>
                          <span className={["job-message"].filter(Boolean).join(" ")}>
                            {job.status_message}
                          </span>
                        </>
                      ) : (
                        <></>
                      )}
                    </div>

                    <div role="cell" className={["job-actions"].filter(Boolean).join(" ")}>
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
                        className={["row-action"].filter(Boolean).join(" ")}
                      >
                        Fire now
                      </button>
                      {!job.run_at_epoch ? (
                        <>
                          <button
                            type="button"
                            disabled={saving.value}
                            onClick={() => edit(job)}
                            className={["row-action"].filter(Boolean).join(" ")}
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
                        className={["row-action"].filter(Boolean).join(" ")}
                      >
                        {job.paused ? "Resume" : "Pause"}
                      </button>
                      <button
                        type="button"
                        disabled={saving.value}
                        onClick={() => void remove(job)}
                        className={["row-action danger-text"].filter(Boolean).join(" ")}
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
                <nav aria-label="Job pages" className={["pagination"].filter(Boolean).join(" ")}>
                  <span>
                    Page {page.value} of {pageCount.value}
                  </span>
                  <div className={["pagination-actions"].filter(Boolean).join(" ")}>
                    <button
                      type="button"
                      disabled={page.value <= 1}
                      onClick={() => changePage(page.value - 1)}
                      className={["toolbar-button"].filter(Boolean).join(" ")}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={page.value >= pageCount.value}
                      onClick={() => changePage(page.value + 1)}
                      className={["toolbar-button"].filter(Boolean).join(" ")}
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
                <footer className={["jobs-footer"].filter(Boolean).join(" ")}>
                  <button
                    type="button"
                    disabled={saving.value}
                    onClick={() => void clearAll()}
                    className={["row-action danger-text"].filter(Boolean).join(" ")}
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

      {editorOpen.value ? (
        <>
          <section
            ref={refs.editorPage}
            aria-labelledby="editor-title"
            tabIndex={-1}
            className={["editor-page"].filter(Boolean).join(" ")}
          >
            <form
              id="job-editor"
              ref={refs.editorForm}
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
              className={["job-editor"].filter(Boolean).join(" ")}
            >
              <div className={["editor-heading"].filter(Boolean).join(" ")}>
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={requestClose}
                  className={["toolbar-button editor-back"].filter(Boolean).join(" ")}
                >
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m12 19-7-7 7-7"></path>
                    <path d="M5 12h14"></path>
                  </svg>
                  Jobs
                </button>
                <div className={["editor-title"].filter(Boolean).join(" ")}>
                  <h2 id="editor-title">
                    {editing.value ? "Edit job" : runOnce.value ? "Run once" : "New job"}
                  </h2>
                  {editing.value ? (
                    <>
                      <span title={editing.value}>{editing.value}</span>
                    </>
                  ) : (
                    <></>
                  )}
                </div>
              </div>

              <div
                className={["editor-body" + (images.value.length ? " has-images" : "")]
                  .filter(Boolean)
                  .join(" ")}
              >
                <div className={["editor-settings"].filter(Boolean).join(" ")}>
                  {!runOnce.value ? (
                    <>
                      <label className={["name-field"].filter(Boolean).join(" ")}>
                        <span>Name</span>
                        <input
                          ref={refs.nameInput}
                          autoComplete="off"
                          readOnly={Boolean(editing.value)}
                          required={true}
                          value={name.value}
                          onChange={(event) => {
                            name.value = event.currentTarget.value;
                          }}
                        />
                      </label>
                    </>
                  ) : (
                    <></>
                  )}

                  <label>
                    <span>Schedule</span>
                    <select
                      disabled={runOnce.value}
                      aria-label="Schedule"
                      value={schedule.value}
                      onChange={(event) => {
                        schedule.value = event.currentTarget.value as "interval" | "daily" | "once";
                      }}
                    >
                      <option value="interval">Interval</option>
                      <option value="daily">Daily</option>
                      <option value="once">Once</option>
                    </select>
                  </label>

                  {schedule.value === "interval" ? (
                    <>
                      <label>
                        <span>Every (minutes)</span>
                        <input
                          type="number"
                          min="0.1"
                          max="43200"
                          step="0.1"
                          required={true}
                          value={interval.value}
                          onChange={(event) => {
                            interval.value = event.currentTarget.value;
                          }}
                        />
                      </label>
                    </>
                  ) : (
                    <>
                      {schedule.value === "once" ? (
                        <>
                          <label>
                            <span>Delay (minutes, 0 = now)</span>
                            <input
                              type="number"
                              min="0"
                              max="43200"
                              step="0.1"
                              required={true}
                              value={onceDelay.value}
                              onChange={(event) => {
                                onceDelay.value = event.currentTarget.value;
                              }}
                            />
                          </label>
                        </>
                      ) : (
                        <>
                          {schedule.value === "daily" ? (
                            <>
                              <label>
                                <span>At (local time)</span>
                                <input
                                  type="time"
                                  required={true}
                                  value={dailyAt.value}
                                  onChange={(event) => {
                                    dailyAt.value = event.currentTarget.value;
                                  }}
                                />
                              </label>
                            </>
                          ) : (
                            <></>
                          )}
                        </>
                      )}
                    </>
                  )}
                </div>

                {schedule.value === "interval" ? (
                  <>
                    <label className={["checkbox-row"].filter(Boolean).join(" ")}>
                      <input
                        type="checkbox"
                        checked={exact.value}
                        onChange={(event) => {
                          exact.value = event.currentTarget.checked;
                        }}
                      />
                      <span>Exact interval</span>
                    </label>
                  </>
                ) : (
                  <>
                    {schedule.value === "once" ? (
                      <>
                        <label className={["checkbox-row"].filter(Boolean).join(" ")}>
                          <input
                            type="checkbox"
                            checked={pinChat.value}
                            onChange={(event) => {
                              pinChat.value = event.currentTarget.checked;
                            }}
                          />
                          <span>Pin chat</span>
                        </label>
                      </>
                    ) : (
                      <></>
                    )}
                  </>
                )}

                <label className={["prompt-field"].filter(Boolean).join(" ")}>
                  <span>Prompt</span>
                  <textarea
                    ref={refs.promptInput}
                    rows={14}
                    required={true}
                    onFocus={() => requestAnimationFrame(keepFocusedPromptVisible)}
                    value={prompt.value}
                    onChange={(event) => {
                      prompt.value = event.currentTarget.value;
                    }}
                  ></textarea>
                </label>
                <div className={["job-image-picker"].filter(Boolean).join(" ")}>
                  <button
                    type="button"
                    disabled={uploadingImage.value || saving.value || images.value.length >= 4}
                    onClick={() => imageInput.value?.click()}
                    className={["toolbar-button"].filter(Boolean).join(" ")}
                  >
                    Add images
                  </button>
                  <input
                    ref={refs.imageInput}
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    multiple={true}
                    disabled={uploadingImage.value || saving.value || images.value.length >= 4}
                    onChange={(event) => void addImages(event.currentTarget)}
                    className={["image-input"].filter(Boolean).join(" ")}
                  />
                  {uploadingImage.value || images.value.length ? (
                    <>
                      <span>
                        {uploadingImage.value ? "Uploading…" : images.value.length + "/4 images"}
                      </span>
                    </>
                  ) : (
                    <></>
                  )}
                </div>
                {images.value.length ? (
                  <>
                    <div
                      ref={refs.imagePreviewList}
                      className={["job-image-previews"].filter(Boolean).join(" ")}
                    >
                      {images.value.map((image, __index) => (
                        <React.Fragment key={image.ref}>
                          <div className={["job-image-preview"].filter(Boolean).join(" ")}>
                            <img src={image.url} alt={image.name} />
                            <span title={image.name}>{image.name}</span>
                            <button
                              type="button"
                              title={"Remove " + image.name}
                              aria-label={"Remove " + image.name}
                              disabled={saving.value || uploadingImage.value}
                              onClick={() =>
                                (images.value = images.value.filter(
                                  (item) => item.ref !== image.ref,
                                ))
                              }
                            >
                              ×
                            </button>
                          </div>
                        </React.Fragment>
                      ))}
                    </div>
                  </>
                ) : (
                  <></>
                )}
              </div>

              <div ref={refs.editorFooter} className={["editor-footer"].filter(Boolean).join(" ")}>
                <div
                  role={confirmDiscard.value ? "alertdialog" : "status"}
                  aria-label={confirmDiscard.value ? "Discard unsaved changes" : undefined}
                  aria-live="polite"
                  className={["editor-feedback"].filter(Boolean).join(" ")}
                >
                  {confirmDiscard.value ? (
                    <>
                      <span>Discard unsaved changes?</span>
                      <button
                        type="button"
                        onClick={() => (confirmDiscard.value = false)}
                        className={["toolbar-button"].filter(Boolean).join(" ")}
                      >
                        Keep editing
                      </button>
                      <button
                        type="button"
                        onClick={discardEditor}
                        className={["toolbar-button danger-text"].filter(Boolean).join(" ")}
                      >
                        Discard
                      </button>
                    </>
                  ) : (
                    <>
                      {editorError.value ? (
                        <>
                          <span className={["editor-error"].filter(Boolean).join(" ")}>
                            {editorError.value}
                          </span>
                        </>
                      ) : (
                        <>
                          {duplicateName.value ? (
                            <>
                              <span className={["editor-error"].filter(Boolean).join(" ")}>
                                This job already exists. Choose another name.
                              </span>
                            </>
                          ) : (
                            <>
                              {dirty.value ? (
                                <>
                                  <span>Unsaved changes</span>
                                </>
                              ) : (
                                <>
                                  {editing.value ? (
                                    <>
                                      <span>No changes</span>
                                    </>
                                  ) : (
                                    <></>
                                  )}
                                </>
                              )}
                            </>
                          )}
                        </>
                      )}
                    </>
                  )}
                </div>
                {!confirmDiscard.value ? (
                  <>
                    <div className={["editor-actions"].filter(Boolean).join(" ")}>
                      <button
                        type="button"
                        disabled={saving.value}
                        onClick={requestClose}
                        className={["toolbar-button"].filter(Boolean).join(" ")}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={
                          saving.value ||
                          uploadingImage.value ||
                          !dirty.value ||
                          duplicateName.value ||
                          !prompt.value.trim() ||
                          (!runOnce.value && !name.value.trim())
                        }
                        className={["primary-button"].filter(Boolean).join(" ")}
                      >
                        {saving.value
                          ? runOnce.value
                            ? "Queuing…"
                            : "Saving…"
                          : editing.value
                            ? "Save changes"
                            : runOnce.value
                              ? Number(onceDelay.value) > 0
                                ? "Schedule once"
                                : "Run once"
                              : "Create job"}
                      </button>
                    </div>
                  </>
                ) : (
                  <></>
                )}
              </div>
            </form>
          </section>
        </>
      ) : (
        <></>
      )}
    </>
  );
}
