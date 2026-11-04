import React, { useLayoutEffect } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import TurnActivity from "./TurnActivity";
import CopyIcon from "./CopyIcon";
import QueueFrontButton from "./QueueFrontButton";
import { ContinueChatIcon, RecoverChatIcon } from "./ChatActionIcons";

import { isVideoAttachment } from "./mediaAttachments";
import {
  chatMessageTime,
  formatStoredResponse,
  partialResponseLabel,
  responseBadge,
  turnStatus,
  workedDurationLabel,
} from "./resultFormatting";

type TranscriptRefs = {
  scrollPane: (element: HTMLDivElement | null) => void;
};

export default function ChatTranscript({
  model,
  refs,
  conversationUrl,
}: {
  model: ReturnType<typeof createChatsPageController>;
  refs: TranscriptRefs;
  conversationUrl: string | null;
}) {
  useSignals();
  const {
    selectedRunId,
    expandedPrompts,
    detail,
    turns,
    startingNewChatFromFailure: startingNewChat,
    requestingManualRecovery,
    requestManualRecovery,
    recoveryPauseSeconds,
    recoveryPauseReason,
    stopping,
    stopJob,
    detailError,
    switchingChat,
    startFailedReplyInNewChat,
    continueUnverifiedInNewChat,
    retryFailedTurn,
    copyText,
    togglePrompt,
    copyState,
  } = model;

  useLayoutEffect(() => {
    model.revealSelectedChat();
  }, [model, detail.value, turns.value]);

  function canManuallyRecoverLatestTurn() {
    const latest = turns.value.findLast((turn) => turn.status !== "cancelled");
    if (!latest) return false;
    // Queued, active, completed and stopped chats are working or settled.
    // Only expose read-only recovery for a broken, verified latest branch.
    return latest.reply_id
      ? Boolean(conversationUrl) && ["interrupted", "outcome_unknown"].includes(latest.status)
      : detail.value?.recovery?.eligible === true &&
          ["interrupted", "unavailable"].includes(latest.status);
  }

  function manualRecoveryLabel() {
    if (requestingManualRecovery.value) return "Requesting recovery…";
    if ((detail.value?.manual_recovery_pending ?? 0) > 0) return "Recovery queued";
    return "Recover chat";
  }

  function manualRecoveryGuidance() {
    if ((detail.value?.manual_recovery_pending ?? 0) <= 0) {
      return "Last resort: check the saved ChatGPT transcript without resending messages.";
    }
    if (recoveryPauseSeconds.value > 0 && recoveryPauseReason.value === "account read cooldown") {
      return `ChatGPT is rate-limiting history reads. Retrying automatically after the cooldown (~${Math.ceil(recoveryPauseSeconds.value / 60)} min).`;
    }
    if (recoveryPauseSeconds.value > 0 && recoveryPauseReason.value === "security cooldown") {
      return "ChatGPT security verification is blocking reads; recovery will retry automatically.";
    }
    return "Waiting to check the saved chat and resume configured permissions.";
  }

  function copyLabel(id: string) {
    if (copyState.value === id) return "Copied";
    if (copyState.value === "error:" + id) return "Copy failed";
    return "Copy";
  }

  function workedDuration(turn: (typeof turns.value)[number], index: number) {
    if (turn.status !== "completed") return null;
    if (index === 0) {
      // History recovery can complete days later; it does not reveal the real work duration.
      return detail.value?.source === "history_dom"
        ? null
        : workedDurationLabel(detail.value?.accepted_at, detail.value?.finished_at);
    }
    return workedDurationLabel(turn.accepted_at, turn.finished_at);
  }

  function queuedFollowupLabel(index: number) {
    const preceding = turns.value[index - 1];
    if (preceding?.status === "queued") return "Follow-up queued · waiting for earlier follow-up";
    if (!preceding?.message_id) return "Follow-up queued · reviving chat";
    return "Follow-up queued · waiting for the preceding response";
  }

  return (
    <div className="chat-transcript-shell">
      <div
        ref={refs.scrollPane}
        onScroll={model.onTranscriptScroll}
        onWheel={model.onTranscriptWheel}
        onTouchStart={model.onTranscriptTouchStart}
        onTouchMove={model.onTranscriptTouchMove}
        onTouchEnd={model.onTranscriptTouchEnd}
        onTouchCancel={model.onTranscriptTouchEnd}
        onKeyDown={model.onTranscriptKeyDown}
        inert={switchingChat.value}
        aria-busy={switchingChat.value}
        className={[
          "chat-transcript-scroll",
          switchingChat.value && detail.value?.send_id === selectedRunId.value
            ? "chat-switch-hidden"
            : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {detail.value ? (
          <>
            <div className="chat-detail-content">
              {turns.value.map((turn, index) => (
                <React.Fragment key={turn.reply_id || detail.value!.send_id}>
                  <div className="message-group user-group">
                    <div className="message-role">
                      <span className="sr-only">
                        You {index === 0 ? <>· Job prompt</> : <>· Reply {index}</>}
                      </span>
                      <time
                        dateTime={new Date(
                          (turn.created_at || detail.value!.created_at) * 1000,
                        ).toISOString()}
                        className="message-timestamp"
                      >
                        {chatMessageTime(turn.created_at || detail.value!.created_at)}
                      </time>
                    </div>
                    <div className="prompt-bubble">
                      <div
                        className={[
                          "prompt-message",
                          turn.user_text.length > 280 &&
                          !expandedPrompts.value[(detail.value?.send_id ?? "") + ":" + index]
                            ? "collapsed"
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        {turn.user_text}
                      </div>
                      {turn.user_text.length > 280 ? (
                        <>
                          <button
                            type="button"
                            aria-expanded={Boolean(
                              expandedPrompts.value[(detail.value?.send_id ?? "") + ":" + index],
                            )}
                            onClick={(event) =>
                              void togglePrompt((detail.value?.send_id ?? "") + ":" + index, event)
                            }
                            className="prompt-expand"
                          >
                            {expandedPrompts.value[(detail.value?.send_id ?? "") + ":" + index]
                              ? "Show less"
                              : "Show full prompt"}
                            <svg
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              aria-hidden="true"
                              className={[
                                "",
                                expandedPrompts.value[(detail.value?.send_id ?? "") + ":" + index]
                                  ? "rotated"
                                  : "",
                              ]
                                .filter(Boolean)
                                .join(" ")}
                            >
                              <path d="m6 9 6 6 6-6"></path>
                            </svg>
                          </button>
                        </>
                      ) : (
                        <></>
                      )}
                    </div>
                    {index === 0 && detail.value!.images?.length ? (
                      <>
                        <div aria-label="Attached files" className="chat-attachments">
                          {detail.value!.images.map((attachment, __index) => (
                            <React.Fragment key={attachment.url}>
                              {isVideoAttachment(attachment.name) ? (
                                <video
                                  src={attachment.url}
                                  controls={true}
                                  playsInline={true}
                                  preload="metadata"
                                  aria-label={attachment.name}
                                />
                              ) : (
                                <a
                                  href={attachment.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={attachment.name}
                                >
                                  <img src={attachment.url} alt={attachment.name} loading="lazy" />
                                </a>
                              )}
                            </React.Fragment>
                          ))}
                        </div>
                      </>
                    ) : (
                      <></>
                    )}
                  </div>
                  <div
                    aria-label={"Assistant response " + (index + 1)}
                    className={["message-group assistant-group response-" + turn.status]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {turn.status !== "generating" && turn.status !== "completed" && (
                      <div className="message-role response-header">
                        <span role="status" className="response-state">
                          {responseBadge(turn.status)}
                        </span>
                      </div>
                    )}
                    {turn.assistant_text ||
                    turn.tool_calls?.length ||
                    turn.display_blocks?.some((block) => block.kind === "text") ? (
                      <>
                        <TurnActivity
                          turn={turn}
                          captureSource={index === 0 ? detail.value!.source : ""}
                          turnTimestamp={turn.created_at || detail.value!.created_at}
                        />
                        {turn.status !== "completed" && turn.status !== "generating" ? (
                          <p className="partial-note">{partialResponseLabel(turn.status)}</p>
                        ) : null}
                        <div className="response-actions">
                          {workedDuration(turn, index) && (
                            <span className="response-worked-duration">
                              {workedDuration(turn, index)}
                            </span>
                          )}
                          <button
                            type="button"
                            aria-label={"Copy assistant reply " + (index + 1)}
                            onClick={() =>
                              copyText(
                                formatStoredResponse(
                                  turn.assistant_text,
                                  index === 0 ? (detail.value?.source ?? "") : "",
                                ),
                                turn.reply_id || selectedRunId.value || "",
                              )
                            }
                            className="copy-message"
                          >
                            <CopyIcon />
                            {copyLabel(turn.reply_id || detail.value!.send_id)}
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        {turn.status !== "generating" && (
                          <p className="no-response">
                            {index > 0 && turn.status === "queued"
                              ? queuedFollowupLabel(index)
                              : turnStatus(turn.status)}
                          </p>
                        )}
                        {index === 0 &&
                          turn.status === "queued" &&
                          model.queueSnapshot.value.waiting_runs?.some(
                            (run) => run.send_id === detail.value?.send_id,
                          ) && (
                            <QueueFrontButton
                              endpoint={
                                "./api/queue/" +
                                encodeURIComponent(detail.value!.send_id) +
                                "/front"
                              }
                              label={detail.value!.title || "chat"}
                              onMoved={model.loadQueue}
                            />
                          )}
                        {turn.status === "preflight_failed" &&
                        turn.reply_id &&
                        turn.conversation_id &&
                        turn.parent_id ? (
                          <>
                            <button
                              type="button"
                              onClick={() => void retryFailedTurn(turn)}
                              className="row-action"
                            >
                              Retry unsent reply
                            </button>
                          </>
                        ) : (
                          <></>
                        )}
                      </>
                    )}

                    {index === turns.value.length - 1 &&
                      turns.value.some((saved) => saved.assistant_text.trim()) &&
                      [
                        "preflight_failed",
                        "interrupted",
                        "unavailable",
                        "outcome_unknown",
                      ].includes(turn.status) && (
                        <div className="chat-recovery-guidance">
                          <button
                            className="row-action chat-action-button"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void startFailedReplyInNewChat(turn)}
                          >
                            <ContinueChatIcon />
                            Continue in new chat
                          </button>
                          {turn.status === "outcome_unknown" && (
                            <span>The original reply may still have been delivered.</span>
                          )}
                        </div>
                      )}
                    {index === 0 &&
                      ["interrupted", "unavailable", "outcome_unknown"].includes(turn.status) &&
                      !detail.value?.conversation_id &&
                      !turn.conversation_id &&
                      !turn.assistant_text.trim() &&
                      Boolean(turn.user_text.trim()) && (
                        <div className="chat-recovery-guidance">
                          <button
                            className="row-action chat-action-button"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void continueUnverifiedInNewChat()}
                          >
                            <ContinueChatIcon />
                            Continue in new chat
                          </button>
                          <p>Original send unverified; continuing starts a separate request.</p>
                        </div>
                      )}
                    {index === 0 &&
                      ["interrupted", "unavailable"].includes(turn.status) &&
                      detail.value?.recovery?.eligible === false &&
                      (Boolean(turn.assistant_text.trim()) || !turn.user_text.trim()) && (
                        <div className="chat-recovery-guidance" role="status">
                          <p>No verified ChatGPT chat for read-only recovery.</p>
                        </div>
                      )}
                    {turn.status === "generating" && (
                      <div className="message-role response-header response-generation-footer">
                        <div className="response-generation" role="status">
                          <span className="response-generation-spark" aria-hidden="true" />
                          <span className="response-state">{responseBadge(turn.status)}</span>
                          <span className="response-generation-title">Generating response</span>
                          <span className="response-generation-dots" aria-hidden="true">
                            <i />
                            <i />
                            <i />
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </React.Fragment>
              ))}
              {canManuallyRecoverLatestTurn() && (
                <div className="chat-manual-recovery">
                  <button
                    type="button"
                    className="row-action chat-action-button"
                    disabled={
                      requestingManualRecovery.value ||
                      (detail.value.manual_recovery_pending ?? 0) > 0
                    }
                    aria-busy={requestingManualRecovery.value}
                    onClick={() => void requestManualRecovery(detail.value!.send_id)}
                  >
                    <RecoverChatIcon />
                    {manualRecoveryLabel()}
                  </button>
                  <button
                    type="button"
                    className="row-action chat-action-button"
                    disabled={Boolean(stopping.value)}
                    onClick={() => void stopJob(detail.value!.send_id)}
                  >
                    {stopping.value ? "Stopping chat…" : "Stop recovery"}
                  </button>
                  <span>{manualRecoveryGuidance()}</span>
                </div>
              )}
              {conversationUrl && (
                <a
                  className="chat-open-chatgpt chat-open-chatgpt-footer"
                  href={conversationUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="Open in ChatGPT"
                  title="Open in ChatGPT"
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
                    <path d="M14 4h6v6m0-6-9 9M20 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h4" />
                  </svg>
                  <span className="chat-open-chatgpt-label">ChatGPT</span>
                </a>
              )}
            </div>
          </>
        ) : (
          <></>
        )}
      </div>
      {switchingChat.value ? (
        <>
          <div
            role="status"
            aria-label={detailError.value ? "Chat unavailable" : "Loading selected chat"}
            className={
              detail.value && !detailError.value ? "chat-switch-cover delayed" : "chat-switch-cover"
            }
          >
            {detailError.value ? (
              <>
                <span className="sr-only">Chat unavailable</span>
              </>
            ) : (
              <>
                <div aria-hidden="true" className="chat-switch-skeleton">
                  <div className="chat-switch-line short"></div>
                  <div className="chat-switch-line prompt"></div>
                  <div className="chat-switch-line medium"></div>
                  <div className="chat-switch-line answer"></div>
                  <div className="chat-switch-line answer last"></div>
                </div>
                <span className="sr-only">Loading selected chat…</span>
              </>
            )}
          </div>
        </>
      ) : (
        <></>
      )}
    </div>
  );
}
