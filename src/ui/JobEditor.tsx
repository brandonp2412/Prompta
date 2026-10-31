import React from "react";
import { useSignals } from "@preact/signals-react/runtime";
import type { createJobsPageController } from "./JobsPageController";

type Controller = ReturnType<typeof createJobsPageController>;

type EditorRefs = {
  editorPage: (element: HTMLElement | null) => void;
  editorForm: (element: HTMLFormElement | null) => void;
  nameInput: (element: HTMLInputElement | null) => void;
  promptInput: (element: HTMLTextAreaElement | null) => void;
  imageInput: (element: HTMLInputElement | null) => void;
  imagePreviewList: (element: HTMLDivElement | null) => void;
  editorFooter: (element: HTMLDivElement | null) => void;
};

export default function JobEditor({ model, refs }: { model: Controller; refs: EditorRefs }) {
  useSignals();
  const {
    saving,
    editing,
    runOnce,
    name,
    schedule,
    interval,
    onceDelay,
    pinChat,
    dailyAt,
    exact,
    prompt,
    images,
    uploadingImage,
    imageInput,
    editorError,
    confirmDiscard,
    dirty,
    duplicateName,
    requestClose,
    discardEditor,
    keepFocusedPromptVisible,
    addImages,
    submit,
  } = model;

  function editorFeedback(): { text: string; error: boolean } {
    if (editorError.value) return { text: editorError.value, error: true };
    if (duplicateName.value)
      return { text: "This job already exists. Choose another name.", error: true };
    if (dirty.value) return { text: "Unsaved changes", error: false };
    if (editing.value) return { text: "No changes", error: false };
    return { text: "", error: false };
  }

  function submitButtonLabel(): string {
    if (saving.value) return runOnce.value ? "Queuing…" : "Saving…";
    if (editing.value) return "Save changes";
    if (!runOnce.value) return "Create job";
    return Number(onceDelay.value) > 0 ? "Schedule once" : "Run once";
  }

  const feedback = editorFeedback();
  const editorModeTitle = runOnce.value ? "Run once" : "New job";

  return (
    <section
      ref={refs.editorPage}
      aria-labelledby="editor-title"
      tabIndex={-1}
      className="editor-page"
    >
      <form
        id="job-editor"
        ref={refs.editorForm}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        className="job-editor"
      >
        <div className="editor-heading">
          <button
            type="button"
            disabled={saving.value}
            onClick={requestClose}
            className="toolbar-button editor-back"
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
          <div className="editor-title">
            <h2 id="editor-title">{editing.value ? "Edit job" : editorModeTitle}</h2>
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
          <div className="editor-settings">
            {!runOnce.value ? (
              <>
                <label className="name-field">
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

            {schedule.value === "interval" && (
              <label>
                <span>Every (minutes)</span>
                <input
                  type="number"
                  min="0.1"
                  max="43200"
                  step="0.1"
                  required
                  value={interval.value}
                  onChange={(event) => (interval.value = event.currentTarget.value)}
                />
              </label>
            )}
            {schedule.value === "once" && (
              <label>
                <span>Delay (minutes, 0 = now)</span>
                <input
                  type="number"
                  min="0"
                  max="43200"
                  step="0.1"
                  required
                  value={onceDelay.value}
                  onChange={(event) => (onceDelay.value = event.currentTarget.value)}
                />
              </label>
            )}
            {schedule.value === "daily" && (
              <label>
                <span>At (local time)</span>
                <input
                  type="time"
                  required
                  value={dailyAt.value}
                  onChange={(event) => (dailyAt.value = event.currentTarget.value)}
                />
              </label>
            )}
          </div>

          {schedule.value === "interval" && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={exact.value}
                onChange={(event) => (exact.value = event.currentTarget.checked)}
              />
              <span>Exact interval</span>
            </label>
          )}
          {schedule.value === "once" && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={pinChat.value}
                onChange={(event) => (pinChat.value = event.currentTarget.checked)}
              />
              <span>Pin chat</span>
            </label>
          )}

          <label className="prompt-field">
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
          <div className="job-image-picker">
            <button
              type="button"
              disabled={uploadingImage.value || saving.value || images.value.length >= 4}
              onClick={() => imageInput.value?.click()}
              className="toolbar-button"
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
              className="image-input"
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
              <div ref={refs.imagePreviewList} className="job-image-previews">
                {images.value.map((image, __index) => (
                  <React.Fragment key={image.ref}>
                    <div className="job-image-preview">
                      <img src={image.url} alt={image.name} />
                      <span title={image.name}>{image.name}</span>
                      <button
                        type="button"
                        title={"Remove " + image.name}
                        aria-label={"Remove " + image.name}
                        disabled={saving.value || uploadingImage.value}
                        onClick={() =>
                          (images.value = images.value.filter((item) => item.ref !== image.ref))
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

        <div ref={refs.editorFooter} className="editor-footer">
          <div
            role={confirmDiscard.value ? "alertdialog" : "status"}
            aria-label={confirmDiscard.value ? "Discard unsaved changes" : undefined}
            aria-live="polite"
            className="editor-feedback"
          >
            {confirmDiscard.value ? (
              <>
                <span>Discard unsaved changes?</span>
                <button
                  type="button"
                  onClick={() => (confirmDiscard.value = false)}
                  className="toolbar-button"
                >
                  Keep editing
                </button>
                <button
                  type="button"
                  onClick={discardEditor}
                  className="toolbar-button danger-text"
                >
                  Discard
                </button>
              </>
            ) : (
              feedback.text && (
                <span className={feedback.error ? "editor-error" : undefined}>{feedback.text}</span>
              )
            )}
          </div>
          {!confirmDiscard.value ? (
            <>
              <div className="editor-actions">
                <button
                  type="button"
                  disabled={saving.value}
                  onClick={requestClose}
                  className="toolbar-button"
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
                  className="primary-button"
                >
                  {submitButtonLabel()}
                </button>
              </div>
            </>
          ) : (
            <></>
          )}
        </div>
      </form>
    </section>
  );
}
