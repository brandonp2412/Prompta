import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createChatsPageController, type Props } from "./ChatsPageController";
import JobsPage from "./JobsPage";
import ChatComposer from "./ChatComposer";
import ResultMarkdown from "./ResultMarkdown";
import ToolCalls from "./ToolCalls";
import { queueEtaExplanation, queueEtaText } from "./queueStatus";
import {
  statusLabel,
  chatMessageTime,
  formatStoredResponse,
  partialResponseLabel,
  plainPreview,
  recoveryProgress,
  turnStatus,
} from "./resultFormatting";
import type { RunSummary, ResultStatus } from "./resultFormatting";
export default function ChatsPage(props: Props) {
  const model = useMemo(() => createChatsPageController(props), []);
  useSignals();
  const {
    retryPins,
    view,
    selectedRunId,
    newChatOpen,
    onSelect,
    statuses,
    responseBadge,
    exactConversationUrl,
    queueSnapshot,
    queueError,
    recoveryPauseSeconds,
    recoveryPauseReason,
    recoveryBacklog,
    recoveryReplyBacklog,
    items,
    pinnedIds,
    pinsReady,
    pinError,
    readError,
    markingAllRead,
    drawerOpen,
    drawerProgress,
    visibleDrawerProgress,
    filtersOpen,
    expandedPrompts,
    search,
    statusFilter,
    detail,
    turns,
    turnsError,
    recoveringReply,
    startingNewChatFromFailure,
    copyState,
    jobsWorkspace,
    loadingList,
    listError,
    morePageFailed,
    detailError,
    pinned,
    replyBlockedReason,
    visibleWaiting,
    unpinned,
    switchingChat,
    selectedChatTitle,
    isUnread,
    retryReadSync,
    markAllRead,
    togglePin,
    loadQueue,
    maybeLoadMore,
    loadList,
    loadMore,
    loadDetail,
    sendFresh,
    freshContinuationPrompt,
    startFailedReplyInNewChat,
    retryFailedInitialInNewChat,
    originalImageRefs,
    sendReply,
    retryFailedTurn,
    copyText,
    applyFilter,
    searchChanged,
    toggleSearch,
    cancelSwipe,
    startSwipe,
    finishSwipe,
    selectRun,
    showJobs,
    createChat,
    escapeDrawer,
    togglePrompt,
  } = model;
  const refs = useMemo(
    () => ({
      sidebarPane: (element: HTMLElement | null) => {
        if (model.sidebarPane.peek() !== (element ?? undefined))
          model.sidebarPane.value = element ?? undefined;
      },
      searchInput: (element: HTMLInputElement | null) => {
        if (model.searchInput.peek() !== (element ?? undefined))
          model.searchInput.value = element ?? undefined;
      },
      listPane: (element: HTMLDivElement | null) => {
        if (model.listPane.peek() !== (element ?? undefined))
          model.listPane.value = element ?? undefined;
      },
      jobsWorkspace: (element: HTMLDivElement | null) => {
        if (model.jobsWorkspace.peek() !== (element ?? undefined))
          model.jobsWorkspace.value = element ?? undefined;
      },
      scrollPane: (element: HTMLDivElement | null) => {
        if (model.scrollPane.peek() !== (element ?? undefined))
          model.scrollPane.value = element ?? undefined;
      },
    }),
    [model],
  );
  useLayoutEffect(() => {
    model.syncProps(props);
  });
  useLayoutEffect(() => {
    if (filtersOpen.value) model.searchInput.peek()?.focus();
  }, [filtersOpen.value, model]);
  useEffect(() => model.mount(), [model]);
  useEffect(() => {
    window.addEventListener("keydown", escapeDrawer);
    window.addEventListener("touchstart", startSwipe);
    window.addEventListener("touchend", finishSwipe);
    window.addEventListener("touchcancel", cancelSwipe);
    return () => {
      window.removeEventListener("keydown", escapeDrawer);
      window.removeEventListener("touchstart", startSwipe);
      window.removeEventListener("touchend", finishSwipe);
      window.removeEventListener("touchcancel", cancelSwipe);
    };
  }, [model]);
  function chatItem(item: RunSummary) {
    return (
      <>
        <div
          className={[
            "chat-entry",
            view.value === "chats" && selectedRunId.value === item.send_id ? "chosen" : "",
            isUnread(item) ? "unread" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <button
            type="button"
            onClick={() => selectRun(item)}
            aria-current={
              view.value === "chats" && selectedRunId.value === item.send_id ? "true" : undefined
            }
            className={["chat-row"].filter(Boolean).join(" ")}
          >
            <span className={["chat-row-top"].filter(Boolean).join(" ")}>
              {isUnread(item) ? (
                <>
                  <span
                    title="Unread reply"
                    className={["unread-indicator"].filter(Boolean).join(" ")}
                  >
                    <span className={["sr-only"].filter(Boolean).join(" ")}>Unread reply</span>
                  </span>
                </>
              ) : (
                <></>
              )}
              <strong>{item.title || "Untitled run"}</strong>
              <span
                title={statusLabel(item.status)}
                className={["result-dot status-" + item.status].filter(Boolean).join(" ")}
              >
                <span className={["sr-only"].filter(Boolean).join(" ")}>
                  {statusLabel(item.status)}
                </span>
              </span>
            </span>
            {item.has_response && item.preview.trim() ? (
              <span className="chat-preview" title={plainPreview(item.preview)}>
                {plainPreview(item.preview)}
              </span>
            ) : (
              <span className="chat-row-meta">
                {statusLabel(item.status)} · {chatMessageTime(item.updated_at || item.created_at)}
              </span>
            )}
          </button>
          <button
            type="button"
            disabled={!pinsReady.value}
            title={pinnedIds.value.includes(item.send_id) ? "Unpin local chat" : "Pin local chat"}
            aria-label={
              pinnedIds.value.includes(item.send_id) ? "Unpin " + item.title : "Pin " + item.title
            }
            aria-pressed={pinnedIds.value.includes(item.send_id)}
            onClick={() => togglePin(item)}
            className={["chat-pin", pinnedIds.value.includes(item.send_id) ? "active" : ""]
              .filter(Boolean)
              .join(" ")}
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
              <path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path>
            </svg>
          </button>
        </div>
      </>
    );
  }
  return (
    <>
      <section
        aria-label="Prompta local chats and jobs"
        className={[
          "chats-layout",
          drawerOpen.value ? "drawer-open" : "",
          drawerProgress.value !== null ? "drawer-interacting" : "",
          view.value === "chats" && !selectedRunId.value && !newChatOpen.value ? "show-list" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={
          {
            "--drawer-offset": `${(visibleDrawerProgress.value - 1) * 100}%`,
            "--drawer-opacity": visibleDrawerProgress.value * 0.6,
          } as React.CSSProperties
        }
      >
        <button
          type="button"
          aria-label="Close chat sidebar"
          tabIndex={drawerOpen.value ? 0 : -1}
          onClick={() => (drawerOpen.value = false)}
          className={["drawer-backdrop"].filter(Boolean).join(" ")}
        ></button>
        <aside
          aria-label="Local chat sidebar"
          ref={refs.sidebarPane}
          className={["chats-sidebar"].filter(Boolean).join(" ")}
        >
          <div className={["sidebar-brand"].filter(Boolean).join(" ")}>
            <div>
              <strong>Prompta</strong>
            </div>
            <button
              type="button"
              aria-label="Close sidebar"
              onClick={() => (drawerOpen.value = false)}
              className={["sidebar-close"].filter(Boolean).join(" ")}
            >
              ×
            </button>
          </div>
          <nav
            aria-label="Main navigation"
            className={["sidebar-actions"].filter(Boolean).join(" ")}
          >
            <button
              type="button"
              onClick={showJobs}
              aria-label="Jobs"
              title="Jobs"
              aria-current={view.value === "jobs" ? "page" : undefined}
              className={["sidebar-jobs", view.value === "jobs" ? "active" : ""]
                .filter(Boolean)
                .join(" ")}
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
                <rect x="4" y="4" width="16" height="16" rx="3"></rect>
                <path d="M8 9h8M8 13h8M8 17h5"></path>
              </svg>
              <span className={["action-label"].filter(Boolean).join(" ")}>Jobs</span>
            </button>
            <button
              type="button"
              onClick={createChat}
              aria-label="New chat"
              title="New chat"
              className={["sidebar-primary"].filter(Boolean).join(" ")}
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
              <span className={["action-label"].filter(Boolean).join(" ")}>New</span>
            </button>
            <button
              type="button"
              aria-label="Search chats"
              title="Search chats"
              aria-expanded={filtersOpen.value}
              aria-controls="chat-filters"
              onClick={toggleSearch}
              className={["sidebar-search", filtersOpen.value ? "active" : ""]
                .filter(Boolean)
                .join(" ")}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <circle cx="10.5" cy="10.5" r="6.5"></circle>
                <path d="m16 16 5 5"></path>
              </svg>
              <span className={["action-label"].filter(Boolean).join(" ")}>Search</span>
              {search.value || statusFilter.value ? (
                <>
                  <span
                    aria-label="Filters active"
                    className={["filter-active-dot"].filter(Boolean).join(" ")}
                  ></span>
                </>
              ) : (
                <></>
              )}
            </button>
          </nav>
          <div className={["sidebar-read-actions"].filter(Boolean).join(" ")}>
            <button
              type="button"
              onClick={markAllRead}
              disabled={markingAllRead.value}
              aria-label="Mark all local chats as read"
              title="Mark all local chats as read"
              className={["mark-all-read"].filter(Boolean).join(" ")}
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
                <path d="m2 12 4 4L16 6M9 12l4 4L23 6"></path>
              </svg>
              {markingAllRead.value ? "Marking as read…" : "Mark all as read"}
            </button>
          </div>
          {filtersOpen.value ? (
            <>
              <div id="chat-filters" className={["chats-controls"].filter(Boolean).join(" ")}>
                <label className={["search-label"].filter(Boolean).join(" ")}>
                  <span className={["sr-only"].filter(Boolean).join(" ")}>Search job results</span>
                  <input
                    type="search"
                    placeholder="Search chats"
                    ref={refs.searchInput}
                    onInput={searchChanged}
                    value={search.value}
                    onChange={(event) => {
                      search.value = event.currentTarget.value;
                    }}
                  />
                </label>
                <label>
                  <span className={["sr-only"].filter(Boolean).join(" ")}>
                    Filter results by state
                  </span>
                  <select
                    value={statusFilter.value}
                    onChange={(event) => {
                      statusFilter.value = event.currentTarget.value as ResultStatus | "";
                      applyFilter();
                    }}
                  >
                    {statuses.map((choice, __index) => (
                      <React.Fragment key={__index}>
                        <option value={choice.value}>{choice.label}</option>
                      </React.Fragment>
                    ))}
                  </select>
                </label>
              </div>
            </>
          ) : (
            <></>
          )}
          {queueError.value ? (
            <>
              <div
                role="alert"
                className={["result-error recovery-error"].filter(Boolean).join(" ")}
              >
                <span>{queueError.value}</span>
                <button type="button" onClick={() => void loadQueue()}>
                  Retry queue status
                </button>
              </div>
            </>
          ) : (
            <></>
          )}
          {listError.value ? (
            <>
              <div
                role="alert"
                className={["result-error recovery-error"].filter(Boolean).join(" ")}
              >
                <span>{listError.value}</span>
                <button
                  type="button"
                  onClick={() => (morePageFailed.value ? void loadMore() : void loadList())}
                >
                  {morePageFailed.value ? "Retry older chats" : "Retry chats"}
                </button>
              </div>
            </>
          ) : (
            <></>
          )}
          {pinError.value ? (
            <>
              <div
                role="alert"
                className={["result-error recovery-error"].filter(Boolean).join(" ")}
              >
                <span>{pinError.value}</span>
                <button
                  type="button"
                  onClick={() => {
                    retryPins();
                  }}
                >
                  Retry pins
                </button>
              </div>
            </>
          ) : (
            <></>
          )}
          {readError.value && (view.value !== "chats" || !selectedRunId.value) ? (
            <>
              <div
                role="alert"
                className={["result-error recovery-error"].filter(Boolean).join(" ")}
              >
                <span>{readError.value}</span>
                <button type="button" onClick={() => void retryReadSync()}>
                  Retry read status
                </button>
              </div>
            </>
          ) : (
            <></>
          )}
          <div
            ref={refs.listPane}
            onScroll={maybeLoadMore}
            className={["chats-list"].filter(Boolean).join(" ")}
          >
            {visibleWaiting.value.length ? (
              <>
                <div
                  aria-live="polite"
                  className={["chats-date queue-heading"].filter(Boolean).join(" ")}
                >
                  <span>Waiting to start · {visibleWaiting.value.length}</span>
                  <span>
                    {queueSnapshot.value.max_workers === null
                      ? "Stage capacity"
                      : `${queueSnapshot.value.occupied_slots}/${queueSnapshot.value.max_workers} global slots`}
                  </span>
                </div>
                {visibleWaiting.value.map((waiting, __index) => (
                  <React.Fragment key={waiting.name}>
                    <div className={["chat-entry queue-waiting"].filter(Boolean).join(" ")}>
                      <button
                        type="button"
                        onClick={showJobs}
                        title={"Open Jobs for " + waiting.name}
                        className={["chat-row"].filter(Boolean).join(" ")}
                      >
                        <span className={["chat-row-top"].filter(Boolean).join(" ")}>
                          <strong>{waiting.name}</strong>
                          <span className={["queue-position"].filter(Boolean).join(" ")}>
                            #{waiting.position} of {queueSnapshot.value.waiting.length}
                          </span>
                        </span>
                        <span
                          className={["queue-subtitle"].filter(Boolean).join(" ")}
                          title={queueEtaExplanation(queueSnapshot.value)}
                        >
                          {queueEtaText(waiting)} ·{" "}
                          {waiting.reason === "stage" ? "stage" : "global"} limit (
                          {waiting.occupied}/{waiting.limit})
                        </span>
                      </button>
                    </div>
                  </React.Fragment>
                ))}
              </>
            ) : (
              <></>
            )}
            {pinned.value.length ? (
              <>
                {pinned.value.map((item, __index) => (
                  <React.Fragment key={item.send_id}>{chatItem(item)}</React.Fragment>
                ))}
              </>
            ) : (
              <></>
            )}
            {loadingList.value && !items.value.length && !pinned.value.length ? (
              <>
                <p className={["chats-empty"].filter(Boolean).join(" ")}>Loading chats…</p>
              </>
            ) : (
              <>
                {!items.value.length && !pinned.value.length && !visibleWaiting.value.length ? (
                  <>
                    <p className={["chats-empty"].filter(Boolean).join(" ")}>
                      {listError.value
                        ? "Chat list temporarily unavailable"
                        : search.value || statusFilter.value
                          ? "No matching chats"
                          : "No chats"}
                    </p>
                  </>
                ) : (
                  <>
                    {unpinned.value.map((item, __index) => (
                      <React.Fragment key={item.send_id}>{chatItem(item)}</React.Fragment>
                    ))}
                  </>
                )}
              </>
            )}
          </div>
        </aside>

        <div className={["chats-detail"].filter(Boolean).join(" ")}>
          <div className={["workspace-header"].filter(Boolean).join(" ")}>
            {view.value === "chats" && selectedRunId.value ? (
              <>
                <button
                  type="button"
                  aria-label="Back to chats"
                  title="Back to chats"
                  onClick={() => onSelect.value(null)}
                  className={["chat-header-back"].filter(Boolean).join(" ")}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="m15 18-6-6 6-6"></path>
                  </svg>
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  aria-label="Open chat sidebar"
                  aria-expanded={drawerOpen.value}
                  onClick={() => (drawerOpen.value = true)}
                  className={["sidebar-menu"].filter(Boolean).join(" ")}
                >
                  ☰
                </button>
              </>
            )}
            <strong>{view.value === "jobs" ? "Jobs" : selectedChatTitle.value}</strong>
          </div>
          {view.value === "jobs" ? (
            <>
              <div
                ref={refs.jobsWorkspace}
                className={["jobs-workspace"].filter(Boolean).join(" ")}
              >
                <JobsPage workspace={jobsWorkspace.value}></JobsPage>
              </div>
            </>
          ) : (
            <>
              {!selectedRunId.value && newChatOpen.value ? (
                <>
                  <div
                    aria-hidden="true"
                    className={["new-chat-empty"].filter(Boolean).join(" ")}
                  ></div>
                </>
              ) : (
                <>
                  {!selectedRunId.value ? (
                    <>
                      <div className={["chats-detail-empty"].filter(Boolean).join(" ")}>
                        <button
                          onClick={createChat}
                          className={["sidebar-primary"].filter(Boolean).join(" ")}
                        >
                          New chat
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      {readError.value ? (
                        <>
                          <div
                            role="alert"
                            className={["result-error recovery-error"].filter(Boolean).join(" ")}
                          >
                            <span>{readError.value}</span>
                            <button type="button" onClick={() => void retryReadSync()}>
                              Retry read status
                            </button>
                          </div>
                        </>
                      ) : (
                        <></>
                      )}
                      <div className={["chat-transcript-shell"].filter(Boolean).join(" ")}>
                        <div
                          ref={refs.scrollPane}
                          inert={switchingChat.value}
                          aria-busy={switchingChat.value}
                          className={[
                            "chat-transcript-scroll",
                            switchingChat.value ? "chat-switch-hidden" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                        >
                          {detailError.value ? (
                            <>
                              <div
                                role="alert"
                                className={["result-error recovery-error"]
                                  .filter(Boolean)
                                  .join(" ")}
                              >
                                <span>{detailError.value}</span>
                                <button
                                  type="button"
                                  onClick={() =>
                                    selectedRunId.value && void loadDetail(selectedRunId.value)
                                  }
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
                              <div className={["chat-detail-content"].filter(Boolean).join(" ")}>
                                {turnsError.value ? (
                                  <>
                                    <div
                                      role="alert"
                                      className={["result-error recovery-error"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    >
                                      <span>{turnsError.value}</span>
                                      <button
                                        type="button"
                                        onClick={() =>
                                          selectedRunId.value &&
                                          void loadDetail(selectedRunId.value)
                                        }
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
                                    <div
                                      className={["message-group user-group"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    >
                                      <div className={["message-role"].filter(Boolean).join(" ")}>
                                        <span className={["sr-only"].filter(Boolean).join(" ")}>
                                          You{" "}
                                          {index === 0 ? <>· Job prompt</> : <>· Reply {index}</>}
                                        </span>
                                        <time
                                          dateTime={new Date(
                                            (turn.created_at || detail.value!.created_at) * 1000,
                                          ).toISOString()}
                                          className={["message-timestamp"]
                                            .filter(Boolean)
                                            .join(" ")}
                                        >
                                          {chatMessageTime(
                                            turn.created_at || detail.value!.created_at,
                                          )}
                                        </time>
                                      </div>
                                      <div className={["prompt-bubble"].filter(Boolean).join(" ")}>
                                        <div
                                          className={[
                                            "prompt-message",
                                            turn.user_text.length > 280 &&
                                            !expandedPrompts.value[
                                              (detail.value?.send_id ?? "") + ":" + index
                                            ]
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
                                                expandedPrompts.value[
                                                  (detail.value?.send_id ?? "") + ":" + index
                                                ],
                                              )}
                                              onClick={(event) =>
                                                void togglePrompt(
                                                  (detail.value?.send_id ?? "") + ":" + index,
                                                  event,
                                                )
                                              }
                                              className={["prompt-expand"]
                                                .filter(Boolean)
                                                .join(" ")}
                                            >
                                              {expandedPrompts.value[
                                                (detail.value?.send_id ?? "") + ":" + index
                                              ]
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
                                                  expandedPrompts.value[
                                                    (detail.value?.send_id ?? "") + ":" + index
                                                  ]
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
                                          <div
                                            aria-label="Attached images"
                                            className={["chat-attachments"]
                                              .filter(Boolean)
                                              .join(" ")}
                                          >
                                            {detail.value!.images.map((attachment, __index) => (
                                              <React.Fragment key={attachment.url}>
                                                <a
                                                  href={attachment.url}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  title={attachment.name}
                                                >
                                                  <img
                                                    src={attachment.url}
                                                    alt={attachment.name}
                                                    loading="lazy"
                                                  />
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
                                      className={[
                                        "message-group assistant-group response-" + turn.status,
                                      ]
                                        .filter(Boolean)
                                        .join(" ")}
                                    >
                                      {turn.status !== "completed" ? (
                                        <>
                                          <div
                                            className={["message-role response-header"]
                                              .filter(Boolean)
                                              .join(" ")}
                                          >
                                            <span
                                              role="status"
                                              className={["response-state"]
                                                .filter(Boolean)
                                                .join(" ")}
                                            >
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
                                              <p
                                                className={["partial-note"]
                                                  .filter(Boolean)
                                                  .join(" ")}
                                              >
                                                {partialResponseLabel(turn.status)}
                                              </p>
                                            </>
                                          ) : (
                                            <></>
                                          )}
                                          <div
                                            className={["response-actions"]
                                              .filter(Boolean)
                                              .join(" ")}
                                          >
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
                                              className={["copy-message"].filter(Boolean).join(" ")}
                                            >
                                              {copyState.value ===
                                              (turn.reply_id || detail.value!.send_id)
                                                ? "Copied"
                                                : copyState.value ===
                                                    "error:" +
                                                      (turn.reply_id || detail.value!.send_id)
                                                  ? "Copy failed"
                                                  : "Copy"}
                                            </button>
                                          </div>
                                        </>
                                      ) : (
                                        <>
                                          <p className={["no-response"].filter(Boolean).join(" ")}>
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
                                                className={["row-action"].filter(Boolean).join(" ")}
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
                                              disabled={startingNewChatFromFailure.value}
                                              aria-busy={startingNewChatFromFailure.value}
                                              onClick={() => void startFailedReplyInNewChat(turn)}
                                            >
                                              Start new chat with last result
                                            </button>
                                            {turn.status === "outcome_unknown" && (
                                              <span>
                                                The original reply may still have been delivered.
                                              </span>
                                            )}
                                          </div>
                                        )}
                                      {index === 0 &&
                                        ["interrupted", "unavailable", "outcome_unknown"].includes(
                                          turn.status,
                                        ) &&
                                        !detail.value?.conversation_id &&
                                        !turn.conversation_id &&
                                        !turn.assistant_text.trim() &&
                                        Boolean(turn.user_text.trim()) && (
                                          <div className="chat-recovery-guidance">
                                            <button
                                              className="row-action"
                                              type="button"
                                              disabled={startingNewChatFromFailure.value}
                                              aria-busy={startingNewChatFromFailure.value}
                                              onClick={() => void retryFailedInitialInNewChat()}
                                            >
                                              Retry original prompt in new chat
                                            </button>
                                            <span>
                                              The first send may have reached ChatGPT. Retrying
                                              explicitly creates a separate chat and could duplicate
                                              it.
                                            </span>
                                          </div>
                                        )}
                                      {index === 0 &&
                                        ["interrupted", "unavailable"].includes(turn.status) &&
                                        detail.value?.recovery?.eligible === false && (
                                          <div className="chat-recovery-guidance" role="status">
                                            {recoveryProgress(
                                              detail.value.recovery,
                                              Date.now() / 1000,
                                            )}
                                            <span>
                                              The capture has no verified ChatGPT conversation to
                                              revisit. No automatic resend will occur.
                                            </span>
                                          </div>
                                        )}
                                      {["interrupted", "unavailable", "outcome_unknown"].includes(
                                        turn.status,
                                      ) &&
                                      exactConversationUrl(
                                        turn.conversation_id || detail.value!.conversation_id,
                                      ) ? (
                                        <>
                                          <div
                                            className={["chat-recovery-guidance"]
                                              .filter(Boolean)
                                              .join(" ")}
                                          >
                                            <span>
                                              Recovery checks are read-only. No automatic resend.
                                            </span>
                                            {recoveryBacklog.value !== null &&
                                              recoveryBacklog.value > 0 && (
                                                <span role="status">
                                                  Recovery backlog: {recoveryBacklog.value} original
                                                  captures
                                                  {recoveryReplyBacklog.value !== null &&
                                                  recoveryReplyBacklog.value > 0
                                                    ? `; ${recoveryReplyBacklog.value} unresolved follow-up captures`
                                                    : ""}
                                                  . Checks are account-paced, so completion may take
                                                  time.
                                                </span>
                                              )}
                                            {index === 0 && detail.value?.recovery && (
                                              <span role="status">
                                                {recoveryProgress(
                                                  detail.value.recovery,
                                                  Date.now() / 1000,
                                                )}
                                              </span>
                                            )}
                                            {recoveryPauseSeconds.value > 0 && (
                                              <span role="status">
                                                Recovery is waiting about{" "}
                                                {Math.ceil(recoveryPauseSeconds.value / 60)} min (
                                                {recoveryPauseReason.value}).
                                              </span>
                                            )}
                                            <a
                                              href={
                                                exactConversationUrl(
                                                  turn.conversation_id ||
                                                    detail.value!.conversation_id,
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
                              aria-label={
                                detailError.value ? "Chat unavailable" : "Loading selected chat"
                              }
                              className={["chat-switch-cover"].filter(Boolean).join(" ")}
                            >
                              {detailError.value ? (
                                <>
                                  <div
                                    className={["result-error recovery-error"]
                                      .filter(Boolean)
                                      .join(" ")}
                                  >
                                    <span>{detailError.value}</span>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        selectedRunId.value && void loadDetail(selectedRunId.value)
                                      }
                                    >
                                      Retry chat
                                    </button>
                                  </div>
                                </>
                              ) : (
                                <>
                                  <div
                                    aria-hidden="true"
                                    className={["chat-switch-skeleton"].filter(Boolean).join(" ")}
                                  >
                                    <div
                                      className={["chat-switch-line short"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    ></div>
                                    <div
                                      className={["chat-switch-line prompt"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    ></div>
                                    <div
                                      className={["chat-switch-line medium"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    ></div>
                                    <div
                                      className={["chat-switch-line answer"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    ></div>
                                    <div
                                      className={["chat-switch-line answer last"]
                                        .filter(Boolean)
                                        .join(" ")}
                                    ></div>
                                  </div>
                                  <span className={["sr-only"].filter(Boolean).join(" ")}>
                                    Loading selected chat…
                                  </span>
                                </>
                              )}
                            </div>
                          </>
                        ) : (
                          <></>
                        )}
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
          {view.value === "chats" && Boolean(selectedRunId.value || newChatOpen.value) ? (
            <>
              <ChatComposer
                mode={selectedRunId.value ? "reply" : "fresh"}
                chatId={selectedRunId.value ?? undefined}
                onSend={selectedRunId.value ? sendReply : sendFresh}
                onFallbackSend={(text) =>
                  sendFresh(freshContinuationPrompt(text), originalImageRefs())
                }
                onNewChat={createChat}
                restoreDraft={
                  selectedRunId.value &&
                  detail.value?.send_id === selectedRunId.value &&
                  turns.value.at(-1)?.status === "preflight_failed"
                    ? (turns.value.at(-1)?.user_text ?? "")
                    : ""
                }
                retryablePreflight={Boolean(
                  selectedRunId.value &&
                  detail.value?.send_id === selectedRunId.value &&
                  turns.value.at(-1)?.status === "preflight_failed",
                )}
                sendDisabled={Boolean(
                  selectedRunId.value &&
                  (detail.value?.send_id !== selectedRunId.value ||
                    replyBlockedReason.value ||
                    recoveringReply.value),
                )}
              ></ChatComposer>
            </>
          ) : (
            <></>
          )}
        </div>
      </section>
    </>
  );
}
