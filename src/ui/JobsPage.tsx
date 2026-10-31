import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createJobsPageController, type Props } from "./JobsPageController";
import JobEditor from "./JobEditor";
import DeliveryDiagnostics from "./DeliveryDiagnostics";
import JobsTable from "./JobsTable";

export default function JobsPage(props: Props) {
  const model = useMemo(() => createJobsPageController(props), []);
  useSignals();
  const {
    jobsLoadError,
    filterOptions,
    jobs,
    activeFilters,
    showRepeatingJobs,
    repeatingJobsCount,
    cadenceJobs,
    filterCounts,
    page,
    visibleJobs,
    allVisiblePaused,
    status,
    saving,
    editorOpen,
    beginNew,
    beginOnce,
    onEditorKeydown,
    toggleFilter,
    load,
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

            {jobsLoadError.value && (
              <div role="alert" className="result-error recovery-error jobs-recovery-error">
                <span>{jobsLoadError.value}</span>
                <button type="button" onClick={() => void load()}>
                  Retry jobs
                </button>
              </div>
            )}

            <DeliveryDiagnostics model={model} />

            <div role="group" aria-label="Filter jobs" className="jobs-summary">
              {filterOptions.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={activeFilters.value[option.key]}
                  title={option.title}
                  onClick={() => toggleFilter(option.key)}
                  className={activeFilters.value[option.key] ? "filter-chip chosen" : "filter-chip"}
                >
                  {option.label} <span>{filterCounts.value[option.key]}</span>
                </button>
              ))}
              <button
                type="button"
                aria-pressed={showRepeatingJobs.value}
                title="Include daily and interval-based repeating jobs"
                onClick={() => {
                  showRepeatingJobs.value = !showRepeatingJobs.value;
                  page.value = 1;
                }}
                className={showRepeatingJobs.value ? "filter-chip chosen" : "filter-chip"}
              >
                Repeating jobs <span>{repeatingJobsCount.value}</span>
              </button>
            </div>

            <JobsTable model={model} />

            {jobs.value.length > 0 && (
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
