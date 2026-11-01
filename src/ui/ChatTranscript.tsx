import React, { useLayoutEffect } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import ResultMarkdown from "./ResultMarkdown";
import ToolCalls from "./ToolCalls";
import { isVideoAttachment } from "./mediaAttachments";
import {
  chatMessageTime,
  formatStoredResponse,
  partialResponseLabel,
  responseBadge,
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
    expandedPrompts,
    detail,
    turns,
    startingNewChatFromFailure: startingNewChat,
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
                    {turn.tool_calls?.length ? (
                      <>
                        <ToolCalls
                          calls={turn.tool_calls}
                          turnTimestamp={turn.created_at || detail.value!.created_at}
                        ></ToolCalls>
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
                        {turn.status !== "completed" && turn.status !== "generating" ? (
                          <p className="partial-note">{partialResponseLabel(turn.status)}</p>
                        ) : null}
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
                        {turn.status !== "generating" && (
                          <p className="no-response">
                            {index > 0 && turn.status === "queued"
                              ? "Follow-up queued · waiting for the preceding response"
                              : turnStatus(turn.status)}
                          </p>
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
                            className="row-action"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void startFailedReplyInNewChat(turn)}
                          >
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
                            className="row-action"
                            type="button"
                            disabled={startingNewChat.value}
                            aria-busy={startingNewChat.value}
                            onClick={() => void continueUnverifiedInNewChat()}
                          >
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
