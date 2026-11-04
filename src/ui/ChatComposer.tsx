import React, { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import {
  createChatComposerController,
  isMobileComposerKeyboard,
  type Props,
} from "./ChatComposerController";
import { rememberComposerImages } from "./composerDraftMemory";
import { attachmentAccept, isVideoAttachment } from "./mediaAttachments";
import { feedbackTone, useToastSignal } from "./toast";
import { ContinueChatIcon } from "./ChatActionIcons";
import {
  activeSlashCommand,
  exactSlashCommand,
  isCommandOnlyDraft,
  suggestedSlashCommands,
  type SlashCommandId,
} from "./slashCommands";
import {
  activeMention,
  insertMention,
  selectedDraftMentions,
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
  const [slashMatch, setSlashMatch] = useState<string | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
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
    // Fit before paint, including when a saved draft hydrates after mount.
    // A deferred animation frame can leave a tall composer until first interaction.
    model.resizeTextarea();
  });
  useEffect(() => model.mount(), [model]);
  useEffect(() => {
    if (props.mode === "fresh" && window.matchMedia("(min-width: 681px)").matches)
      model.textarea.peek()?.focus();
  }, [model, props.mode, props.chatId]);

  useEffect(() => {
    setMentionMatch(null);
    setMentionDismissed(false);
    setSlashMatch(null);
    setSlashDismissed(false);
  }, [props.chatId, props.mode]);

  const mentionOptions =
    mentionMatch && !mentionDismissed && !model.sending.value && !model.disabled.value
      ? suggestedMentions(mentionMatch.query)
      : [];
  const slashOptions =
    slashMatch !== null && !slashDismissed && !model.sending.value && !model.disabled.value
      ? suggestedSlashCommands(slashMatch)
      : [];
  const selectedMentions = selectedDraftMentions(draft.value);

  function updateMention(element: HTMLTextAreaElement, edited = false) {
    if (edited) {
      setMentionDismissed(false);
      setSlashDismissed(false);
    }
    if (element.selectionStart !== element.selectionEnd) {
      setMentionMatch(null);
      setSlashMatch(null);
      return;
    }
    setMentionMatch(activeMention(element.value, element.selectionStart));
    setMentionIndex(0);
    setSlashMatch(activeSlashCommand(element.value, element.selectionStart));
    setSlashIndex(0);
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

  function executeSlash(id: SlashCommandId) {
    model.setDraft("");
    setSlashMatch(null);
    setMentionMatch(null);
    setSlashDismissed(true);
    if (id === "help") {
      model.setDraft("/");
      setSlashMatch("");
      setSlashIndex(0);
      setSlashDismissed(false);
      requestAnimationFrame(() => model.textarea.peek()?.focus());
    } else if (id !== "clear") {
      void props.onCommand?.(id);
    }
  }

  function chooseSlash(index: number) {
    const option = slashOptions[index];
    if (option) executeSlash(option.id);
  }

  function submitOrRunCommand() {
    const text = model.draft.peek();
    if (isCommandOnlyDraft(text)) {
      const command = exactSlashCommand(text);
      if (command) executeSlash(command.id);
      else model.feedback.value = `Unknown command: ${text.trim()}. Type /help to see commands.`;
      return;
    }
    if (showStop.value) void stop();
    else void submit();
  }

  function removeSelectedMention(start: number, end: number) {
    const text = model.draft.peek();
    const removeEnd = text[end] === " " ? end + 1 : end;
    model.setDraft(text.slice(0, start) + text.slice(removeEnd));
    setMentionMatch(null);
    setMentionDismissed(true);
    requestAnimationFrame(() => {
      const element = model.textarea.peek();
      element?.focus();
      element?.setSelectionRange(start, start);
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
  let autocompleteControls: string | undefined;
  let autocompleteActiveOption: string | undefined;
  if (slashOptions.length) {
    autocompleteControls = "composer-slash-options";
    autocompleteActiveOption = `composer-slash-option-${slashIndex}`;
  } else if (mentionOptions.length) {
    autocompleteControls = "composer-mention-options";
    autocompleteActiveOption = `composer-mention-option-${mentionIndex}`;
  }

  return (
    <>
      <form
        aria-label={mode.value === "fresh" ? "New chat composer" : "Reply composer"}
        onSubmit={(event) => {
          event.preventDefault();
          submitOrRunCommand();
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
        {slashOptions.length > 0 && (
          <div
            className="composer-mentions composer-slash"
            role="listbox"
            id="composer-slash-options"
            aria-label="Slash commands"
          >
            <div className="composer-mentions-heading">
              Commands · ↑ ↓ to navigate · Enter to run
            </div>
            {slashOptions.map((option, index) => (
              <button
                type="button"
                role="option"
                id={`composer-slash-option-${index}`}
                aria-selected={index === slashIndex}
                className={index === slashIndex ? "selected" : ""}
                key={option.id}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => chooseSlash(index)}
              >
                <span className="composer-mention-icon" aria-hidden="true">
                  {option.icon}
                </span>
                <span className="composer-mention-label">
                  <strong>/{option.name}</strong>
                  <small>{option.description}</small>
                </span>
                <span className="composer-command-aliases">
                  {option.aliases
                    .slice(0, 2)
                    .map((alias) => `/${alias}`)
                    .join(" · ")}
                </span>
              </button>
            ))}
          </div>
        )}
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
          {selectedMentions.length > 0 && (
            <div className="composer-selected-mentions" aria-label="Selected tools and connectors">
              {selectedMentions.map(({ start, end, mention }) => (
                <button
                  key={`${start}-${mention.name}`}
                  type="button"
                  className="composer-selected-mention"
                  aria-label={`Remove @${mention.name}`}
                  title={`Remove @${mention.name}`}
                  disabled={sending.value || disabled.value}
                  onClick={() => removeSelectedMention(start, end)}
                >
                  <span className="composer-selected-mention-icon" aria-hidden="true">
                    {mention.kind === "tool" ? "✦" : "@"}
                  </span>
                  <span className="composer-selected-mention-name">{mention.name}</span>
                  <span className="composer-selected-mention-remove" aria-hidden="true">
                    ×
                  </span>
                </button>
              ))}
            </div>
          )}
          <textarea
            ref={refs.textarea}
            onInput={(event) => {
              draftChanged(event);
              updateMention(event.currentTarget, true);
            }}
            onKeyDown={(event) => {
              // Mobile Return is text input, never Send or autocomplete selection.
              if (event.key === "Enter" && isMobileComposerKeyboard()) return;
              if (slashOptions.length) {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                  event.preventDefault();
                  setSlashIndex(
                    (previous) =>
                      (previous + (event.key === "ArrowDown" ? 1 : -1) + slashOptions.length) %
                      slashOptions.length,
                  );
                  return;
                }
                if (
                  (event.key === "Enter" || event.key === "Tab") &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  chooseSlash(slashIndex);
                  return;
                }
              }
              if (event.key === "Escape" && slashMatch !== null) {
                event.preventDefault();
                setSlashDismissed(true);
                return;
              }
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing &&
                isCommandOnlyDraft(model.draft.peek())
              ) {
                event.preventDefault();
                submitOrRunCommand();
                return;
              }
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
              if (!mentionDismissed || !slashDismissed) updateMention(event.currentTarget);
            }}
            onKeyUp={(event) => {
              if (
                !["Escape", "ArrowDown", "ArrowUp", "Enter", "Tab"].includes(event.key) &&
                (!mentionDismissed || !slashDismissed)
              )
                updateMention(event.currentTarget);
            }}
            onBlur={() => {
              setMentionMatch(null);
              setSlashMatch(null);
            }}
            aria-autocomplete="list"
            aria-expanded={slashOptions.length > 0 || mentionOptions.length > 0}
            aria-controls={autocompleteControls}
            aria-activedescendant={autocompleteActiveOption}
            onPaste={pasted}
            rows={1}
            enterKeyHint="enter"
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
