import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createChatComposerController, type Props } from "./ChatComposerController";
import { rememberComposerImages } from "./composerDraftMemory";
export default function ChatComposer(props: Props) {
  const model = useMemo(() => createChatComposerController(props), []);
  useSignals();
  const {
    mode,
    onFallbackSend,
    onNewChat,
    disabled,
    draft,
    images,
    uploading,
    sending,
    feedback,
    fallbackAvailable,
    dragging,
    fileInput,
    draftStorageKey,
    canAttach,
    hasDraft,
    canSend,
    draftChanged,
    addFiles,
    submit,
    keydown,
    pasted,
    dropped,
  } = model;
  const refs = useMemo(
    () => ({
      textarea: (element: HTMLTextAreaElement | null) => {
        if (model.textarea.peek() !== (element ?? undefined))
          model.textarea.value = element ?? undefined;
      },
      fileInput: (element: HTMLInputElement | null) => {
        if (model.fileInput.peek() !== (element ?? undefined))
          model.fileInput.value = element ?? undefined;
      },
    }),
    [model],
  );
  useLayoutEffect(() => {
    model.syncProps(props);
  });
  useEffect(() => model.mount(), [model]);

  return (
    <>
      <form
        aria-label={mode.value === "fresh" ? "New chat composer" : "Reply composer"}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          dragging.value = mode.value === "fresh";
        }}
        onDragLeave={() => (dragging.value = false)}
        onDrop={dropped}
        className={["chat-composer-wrap", dragging.value ? "dragging" : ""]
          .filter(Boolean)
          .join(" ")}
      >
        <div className={["chat-composer"].filter(Boolean).join(" ")}>
          {images.value.length ? (
            <>
              <div
                aria-label="Images to attach"
                className={["composer-previews"].filter(Boolean).join(" ")}
              >
                {images.value.map((image, __index) => (
                  <React.Fragment key={image.ref}>
                    <div className={["composer-preview"].filter(Boolean).join(" ")}>
                      <img src={image.url} alt={image.name} />
                      <button
                        type="button"
                        aria-label={"Remove " + image.name}
                        disabled={!canAttach.value}
                        onClick={() => {
                          images.value = images.value.filter((item) => item.ref !== image.ref);
                          rememberComposerImages(draftStorageKey.value, images.value);
                        }}
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
          <textarea
            ref={refs.textarea}
            onInput={draftChanged}
            onKeyDown={keydown}
            onPaste={pasted}
            rows={1}
            maxLength={32000}
            disabled={disabled.value}
            readOnly={sending.value}
            aria-busy={sending.value}
            aria-label={
              mode.value === "fresh" ? "Message for new chat" : "Message for current chat"
            }
            placeholder="Message Prompta…"
            value={draft.value}
            onChange={(event) => {
              draft.value = event.currentTarget.value;
            }}
          ></textarea>
          <div className={["composer-actions"].filter(Boolean).join(" ")}>
            <div className={["composer-attach"].filter(Boolean).join(" ")}>
              {mode.value === "fresh" ? (
                <>
                  <button
                    type="button"
                    aria-label="Attach images"
                    title="Attach images"
                    disabled={!canAttach.value}
                    onClick={() => fileInput.value?.click()}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="m20.5 11.5-8.7 8.7a5.5 5.5 0 0 1-7.8-7.8l9.4-9.4a3.7 3.7 0 0 1 5.2 5.2l-9.4 9.4a1.9 1.9 0 0 1-2.7-2.7l8.6-8.6"></path>
                    </svg>
                    <span>
                      {images.value.length
                        ? `Add images (${images.value.length}/4)`
                        : "Attach images"}
                    </span>
                  </button>
                  <input
                    ref={refs.fileInput}
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    multiple={true}
                    aria-label="Choose images"
                    disabled={!canAttach.value}
                    onChange={(event) => {
                      void addFiles(Array.from(event.currentTarget.files || []));
                      event.currentTarget.value = "";
                    }}
                  />
                </>
              ) : (
                <></>
              )}
              {uploading.value ? (
                <>
                  <small role="status">Uploading images…</small>
                </>
              ) : (
                <></>
              )}
            </div>
            {!hasDraft.value && images.value.length === 0 && !uploading.value && !sending.value ? (
              <>
                <button
                  type="button"
                  disabled={disabled.value || uploading.value}
                  onClick={onNewChat.value}
                  aria-label="New chat"
                  title="New chat"
                  className={["composer-send composer-new-chat"].filter(Boolean).join(" ")}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z"></path>
                  </svg>
                </button>
              </>
            ) : (
              <>
                <button
                  type="submit"
                  disabled={!canSend.value}
                  aria-label={
                    sending.value
                      ? "Sending"
                      : mode.value === "fresh"
                        ? "Send fresh chat"
                        : "Send reply"
                  }
                  className={["composer-send"].filter(Boolean).join(" ")}
                >
                  {sending.value ? (
                    <>
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        aria-hidden="true"
                        className={["composer-send-spinner"].filter(Boolean).join(" ")}
                      >
                        <path d="M12 3a9 9 0 1 1-9 9"></path>
                      </svg>
                    </>
                  ) : (
                    <>
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M12 19V5m-6 6 6-6 6 6"></path>
                      </svg>
                    </>
                  )}
                </button>
              </>
            )}
          </div>
        </div>
        {feedback.value ? (
          <>
            <p role="status" className={["composer-feedback"].filter(Boolean).join(" ")}>
              {feedback.value}
            </p>
          </>
        ) : (
          <></>
        )}
        {fallbackAvailable.value && onFallbackSend.value && hasDraft.value ? (
          <>
            <button
              type="button"
              disabled={sending.value}
              onClick={() => void submit(true)}
              className={["composer-fallback"].filter(Boolean).join(" ")}
            >
              Start new chat with last result
            </button>
          </>
        ) : (
          <></>
        )}
      </form>
    </>
  );
}
