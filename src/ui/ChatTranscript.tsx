import React from "react";
import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import ResultMarkdown from "./ResultMarkdown";
import ToolCalls from "./ToolCalls";
import {
  chatMessageTime,
  formatStoredResponse,
  partialResponseLabel,
  recoveryProgress,
  responseBadge,
  exactConversationUrl,
  turnStatus,
} from "./resultFormatting";

type TranscriptRefs = {
  scrollPane: (element: HTMLDivElement | null) => void;
};

export default function ChatTranscript({
  model,
  refs,
}: {
  model: ReturnType<typeof createChatsPageController>;
  refs: TranscriptRefs;
}) {
  useSignals();
  const {
    selectedRunId,
    recoveryPauseSeconds: pauseSeconds,
    recoveryPauseReason: pauseReason,
    recoveryBacklog: recoveryQueue,
    recoveryUnverified: unverifiedCaptures,
    recoveryReplyBacklog: replyQueue,
    expandedPrompts,
    detail,
    turns,
    turnsError,
    startingNewChatFromFailure: startingNewChat,
    detailError,
    switchingChat,
    loadDetail,
    startFailedReplyInNewChat,
    retryFailedInitialInNewChat,
    retryFailedTurn,
    copyText,
    togglePrompt,
    copyState,
  } = model;

  function copyLabel(id: string) {
    if (copyState.value === id) return "Copied";
    if (copyState.value === "error:" + id) return "Copy failed";
    return "Copy";
  }

  return (
    <div className="chat-transcript-shell">
      <div
        ref={refs.scrollPane}
        inert={switchingChat.value}
        aria-busy={switchingChat.value}
        className={["chat-transcript-scroll", switchingChat.value ? "chat-switch-hidden" : ""]
          .filter(Boolean)
          .join(" ")}
      >
        {detailError.value ? (
          <>
            <div role="alert" className="result-error recovery-error">
              <span>{detailError.value}</span>
              <button
                type="button"
                onClick={() => selectedRunId.value && void loadDetail(selectedRunId.value)}
              >
                Retry chat
              </button>
            </div>
          </>
        ) : (
          <></>
        )}

        {detail.value ? (
          <>
            <div className="chat-detail-content">
              {turnsError.value ? (
                <>
                  <div role="alert" className="result-error recovery-error">
                    <span>{turnsError.value}</span>
                    <button
                      type="button"
                      onClick={() => selectedRunId.value && void loadDetail(selectedRunId.value)}
                    >
                      Retry replies
                    </button>
                  </div>
                </>
              ) : (
                <></>
              )}
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
                        <div aria-label="Attached images" className="chat-attachments">
                          {detail.value!.images.map((attachment, __index) => (
                            <React.Fragment key={attachment.url}>
                              <a
                                href={attachment.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                title={attachment.name}
                              >
                                <img src={attachment.url} alt={attachment.name} loading="lazy" />
                              </a>
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
                    {turn.status !== "completed" ? (
                      <>
                        <div className="message-role response-header">
                          <span role="status" className="response-state">
                            {responseBadge(turn.status)}
                          </span>
                        </div>
                      </>
                    ) : (
                      <></>
                    )}
                    {turn.tool_calls?.length ? (
                      <>
                        <ToolCalls calls={turn.tool_calls}></ToolCalls>
                      </>
                    ) : (
                      <></>
                    )}
                    {turn.assistant_text ? (
                      <>
                        <ResultMarkdown
                          source={turn.assistant_text}
                          captureSource={index === 0 ? detail.value!.source : ""}
                        ></ResultMarkdown>
                        {turn.status !== "completed" ? (
                          <>
                            <p className="partial-note">{partialResponseLabel(turn.status)}</p>
                          </>
                        ) : (
                          <></>
                        )}
                        <div className="response-actions">
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
                            {copyLabel(turn.reply_id || detail.value!.send_id)}
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="no-response">
                          {index > 0 && turn.status === "queued"
                            ? "Follow-up queued · waiting for the preceding response"
                            : turnStatus(turn.status)}
                        </p>
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
                              Retry this follow-up
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
                            className="row-action"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void startFailedReplyInNewChat(turn)}
                          >
                            Start new chat with last result
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
                            className="row-action"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void retryFailedInitialInNewChat()}
                          >
                            Retry original prompt in new chat
                          </button>
                          <span>
                            The first send may have reached ChatGPT. Retrying explicitly creates a
                            separate chat and could duplicate it.
                          </span>
                        </div>
                      )}
                    {index === 0 &&
                      ["interrupted", "unavailable"].includes(turn.status) &&
                      detail.value?.recovery?.eligible === false && (
                        <div className="chat-recovery-guidance" role="status">
                          {recoveryProgress(detail.value.recovery, Date.now() / 1000)}
                          <span>
                            The capture has no verified ChatGPT conversation to revisit. No
                            automatic resend will occur.
                          </span>
                        </div>
                      )}
                    {["interrupted", "unavailable", "outcome_unknown"].includes(turn.status) &&
                    exactConversationUrl(turn.conversation_id || detail.value!.conversation_id) ? (
                      <>
                        <div className="chat-recovery-guidance">
                          <span>Recovery checks are read-only. No automatic resend.</span>
                          {recoveryQueue.value !== null && recoveryQueue.value > 0 && (
                            <span role="status">
                              Recovery backlog: {recoveryQueue.value} original captures
                              {replyQueue.value !== null && replyQueue.value > 0
                                ? `; ${replyQueue.value} unresolved follow-up captures`
                                : ""}
                              . Checks are account-paced, so completion may take time.
                            </span>
                          )}
                          {unverifiedCaptures.value !== null && unverifiedCaptures.value > 0 && (
                            <span role="status">
                              {unverifiedCaptures.value} original captures lack a verified ChatGPT
                              conversation, so automatic recovery cannot check them.
                            </span>
                          )}
                          {index === 0 && detail.value?.recovery && (
                            <span role="status">
                              {recoveryProgress(detail.value.recovery, Date.now() / 1000)}
                            </span>
                          )}
                          {pauseSeconds.value > 0 && (
                            <span role="status">
                              Recovery is waiting about {Math.ceil(pauseSeconds.value / 60)} min (
                              {pauseReason.value}).
                            </span>
                          )}
                          <a
                            href={
                              exactConversationUrl(
                                turn.conversation_id || detail.value!.conversation_id,
                              ) ?? undefined
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Open exact chat in ChatGPT
                          </a>
                        </div>
                      </>
                    ) : (
                      <></>
                    )}
                  </div>
                </React.Fragment>
              ))}
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
            className="chat-switch-cover"
          >
            {detailError.value ? (
              <>
                <div className="result-error recovery-error">
                  <span>{detailError.value}</span>
                  <button
                    type="button"
                    onClick={() => selectedRunId.value && void loadDetail(selectedRunId.value)}
                  >
                    Retry chat
                  </button>
                </div>
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
