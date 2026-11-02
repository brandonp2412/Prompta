import React, { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createChatComposerController, type Props } from "./ChatComposerController";
import { rememberComposerImages } from "./composerDraftMemory";
import { attachmentAccept, isVideoAttachment } from "./mediaAttachments";
import { feedbackTone, useToastSignal } from "./toast";
import { ContinueChatIcon } from "./ChatActionIcons";
import {
  activeMention,
  insertMention,
  suggestedMentions,
  type MentionMatch,
} from "./composerMentions";
export default function ChatComposer(props: Props) {
  const model = useMemo(() => createChatComposerController(props), []);
  useSignals();
  useToastSignal(model.feedback, { tone: feedbackTone, immediate: true });
  const [mentionMatch, setMentionMatch] = useState<MentionMatch | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionDismissed, setMentionDismissed] = useState(false);
  const {
    mode,
    onFallbackSend,
    onNewChat,
    disabled,
    draft,
    images,
    uploading,
    sending,
    fallbackAvailable,
    offerFreshContinuation,
    dragging,
    fileInput,
    draftStorageKey,
    canAttach,
    hasDraft,
    canSend,
    canFallback,
    draftChanged,
    addFiles,
    showStop,
    stopping,
    stop,
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
  useEffect(() => {
    if (props.mode === "fresh" && window.matchMedia("(min-width: 681px)").matches)
      model.textarea.peek()?.focus();
  }, [model, props.mode, props.chatId]);

  useEffect(() => {
    setMentionMatch(null);
    setMentionDismissed(false);
  }, [props.chatId, props.mode]);

  const mentionOptions =
    mentionMatch && !mentionDismissed && !model.sending.value && !model.disabled.value
      ? suggestedMentions(mentionMatch.query)
      : [];

  function updateMention(element: HTMLTextAreaElement, edited = false) {
    if (edited) setMentionDismissed(false);
    if (element.selectionStart !== element.selectionEnd) {
      setMentionMatch(null);
      return;
    }
    setMentionMatch(activeMention(element.value, element.selectionStart));
    setMentionIndex(0);
  }

  function chooseMention(index: number) {
    const match = mentionMatch;
    const option = mentionOptions[index];
    if (!match || !option) return;
    const next = insertMention(model.draft.peek(), match, option.name);
    model.setDraft(next.value);
    setMentionMatch(null);
    // Programmatic cursor placement fires onSelect; keep the menu closed until
    // the next user edit instead of reopening for the inserted trailing space.
    setMentionDismissed(true);
    requestAnimationFrame(() => {
      const element = model.textarea.peek();
      element?.focus();
      element?.setSelectionRange(next.cursor, next.cursor);
    });
  }

  function sendLabel() {
    if (sending.value) return "Sending";
    return mode.value === "fresh" ? "Send fresh chat" : "Send reply";
  }
  const showNewChat =
    !showStop.value &&
    !hasDraft.value &&
    images.value.length === 0 &&
    !uploading.value &&
    !sending.value;

  return (
    <>
      <form
        aria-label={mode.value === "fresh" ? "New chat composer" : "Reply composer"}
        onSubmit={(event) => {
          event.preventDefault();
          if (showStop.value) void stop();
          else void submit();
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
        {mentionOptions.length > 0 && (
          <div
            className="composer-mentions"
            role="listbox"
            id="composer-mention-options"
            aria-label="Tools and connectors"
          >
            <div className="composer-mentions-heading">Tools and connectors</div>
            {mentionOptions.map((option, index) => (
              <button
                type="button"
                role="option"
                id={`composer-mention-option-${index}`}
                aria-selected={index === mentionIndex}
                className={index === mentionIndex ? "selected" : ""}
                key={option.name}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => chooseMention(index)}
              >
                <span className="composer-mention-icon">{option.kind === "tool" ? "✦" : "@"}</span>
                <span className="composer-mention-label">
                  <strong>{option.name}</strong>
                  <small>{option.description}</small>
                </span>
                <span className="composer-mention-kind">{option.kind}</span>
              </button>
            ))}
          </div>
        )}
        <div className="chat-composer">
          {images.value.length ? (
            <>
              <div aria-label="Attachments to send" className="composer-previews">
                {images.value.map((image, __index) => (
                  <React.Fragment key={image.ref}>
                    <div className="composer-preview">
                      {isVideoAttachment(image.name) ? (
                        <div className="composer-video" title={image.name}>
                          <video
                            src={image.url}
                            muted={true}
                            playsInline={true}
                            preload="metadata"
                          />
                          <span>Video</span>
                        </div>
                      ) : (
                        <img src={image.url} alt={image.name} />
                      )}
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
            onInput={(event) => {
              draftChanged(event);
              updateMention(event.currentTarget, true);
            }}
            onKeyDown={(event) => {
              if (mentionOptions.length) {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                  event.preventDefault();
                  setMentionIndex(
                    (previous) =>
                      (previous + (event.key === "ArrowDown" ? 1 : -1) + mentionOptions.length) %
                      mentionOptions.length,
                  );
                  return;
                }
                if (event.key === "Enter" || event.key === "Tab") {
                  if (!event.nativeEvent.isComposing) {
                    event.preventDefault();
                    chooseMention(mentionIndex);
                  }
                  return;
                }
              }
              if (event.key === "Escape" && mentionMatch) {
                event.preventDefault();
                setMentionDismissed(true);
                return;
              }
              keydown(event);
            }}
            onSelect={(event) => {
              if (!mentionDismissed) updateMention(event.currentTarget);
            }}
            onKeyUp={(event) => {
              if (
                !["Escape", "ArrowDown", "ArrowUp", "Enter", "Tab"].includes(event.key) &&
                !mentionDismissed
              )
                updateMention(event.currentTarget);
            }}
            onBlur={() => setMentionMatch(null)}
            aria-autocomplete="list"
            aria-expanded={mentionOptions.length > 0}
            aria-controls={mentionOptions.length ? "composer-mention-options" : undefined}
            aria-activedescendant={
              mentionOptions.length ? `composer-mention-option-${mentionIndex}` : undefined
            }
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
          <div className="composer-actions">
            <div className="composer-attach">
              {mode.value === "fresh" ? (
                <>
                  <button
                    type="button"
                    aria-label="Attach photos or videos"
                    title="Attach photos or videos"
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
                        ? `Add attachments (${images.value.length}/4)`
                        : "Attach photos or videos"}
                    </span>
                  </button>
                  <input
                    ref={refs.fileInput}
                    type="file"
                    accept={attachmentAccept}
                    multiple={true}
                    aria-label="Choose photos or videos"
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
                  <small role="status">Uploading attachments…</small>
                </>
              ) : (
                <></>
              )}
            </div>
            {showStop.value && (
              <button
                type="button"
                disabled={stopping.value || disabled.value}
                aria-label={stopping.value ? "Stopping chat" : "Stop generating"}
                title={stopping.value ? "Stopping chat…" : "Stop generating"}
                className="composer-send composer-stop"
                onClick={() => void stop()}
              >
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <rect x="7" y="7" width="10" height="10" rx="2"></rect>
                </svg>
              </button>
            )}
            {showNewChat && (
              <>
                <button
                  type="button"
                  disabled={disabled.value || uploading.value}
                  onClick={onNewChat.value}
                  aria-label="New chat"
                  title="New chat"
                  className="composer-send composer-new-chat"
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
            )}
            {!showStop.value && !showNewChat && (
              <>
                <button
                  type="submit"
                  disabled={!canSend.value}
                  aria-label={sendLabel()}
                  className="composer-send"
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
                        className="composer-send-spinner"
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
        {mode.value === "reply" &&
        (fallbackAvailable.value || offerFreshContinuation.value) &&
        onFallbackSend.value &&
        hasDraft.value ? (
          <>
            <button
              type="button"
              disabled={!canFallback.value}
              onClick={() => void submit(true)}
              className="composer-fallback chat-action-button"
            >
              <ContinueChatIcon />
              Continue in new chat
            </button>
          </>
        ) : (
          <></>
        )}
      </form>
    </>
  );
}
