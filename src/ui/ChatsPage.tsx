import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createChatsPageController, type Props } from "./ChatsPageController";
import JobsPage from "./JobsPage";
import ChatComposer from "./ChatComposer";
import ChatsSidebar from "./ChatsSidebar";
import ChatTranscript from "./ChatTranscript";
export default function ChatsPage(props: Props) {
  const model = useMemo(() => createChatsPageController(props), []);
  useSignals();
  const {
    view,
    selectedRunId,
    newChatOpen,
    onSelect,
    readError,
    drawerOpen,
    drawerProgress,
    visibleDrawerProgress,
    filtersOpen,
    detail,
    turns,
    recoveringReply,
    jobsWorkspace,
    replyBlockedReason,
    selectedChatTitle,
    retryReadSync,
    sendFresh,
    freshContinuationPrompt,
    originalImageRefs,
    sendReply,
    cancelSwipe,
    startSwipe,
    finishSwipe,
    createChat,
    escapeDrawer,
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
          className="drawer-backdrop"
        ></button>
        <ChatsSidebar model={model} refs={refs} />

        <div className="chats-detail">
          <div className="workspace-header">
            {view.value === "chats" && selectedRunId.value ? (
              <>
                <button
                  type="button"
                  aria-label="Back to chats"
                  title="Back to chats"
                  onClick={() => onSelect.value(null)}
                  className="chat-header-back"
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
                  className="sidebar-menu"
                >
                  ☰
                </button>
              </>
            )}
            <strong>{view.value === "jobs" ? "Jobs" : selectedChatTitle.value}</strong>
          </div>
          {view.value === "jobs" ? (
            <>
              <div ref={refs.jobsWorkspace} className="jobs-workspace">
                <JobsPage workspace={jobsWorkspace.value}></JobsPage>
              </div>
            </>
          ) : (
            <>
              {!selectedRunId.value && newChatOpen.value ? (
                <>
                  <div aria-hidden="true" className="new-chat-empty"></div>
                </>
              ) : (
                <>
                  {!selectedRunId.value ? (
                    <>
                      <div className="chats-detail-empty">
                        <button onClick={createChat} className="sidebar-primary">
                          New chat
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      {readError.value ? (
                        <>
                          <div role="alert" className="result-error recovery-error">
                            <span>{readError.value}</span>
                            <button type="button" onClick={() => void retryReadSync()}>
                              Retry read status
                            </button>
                          </div>
                        </>
                      ) : (
                        <></>
                      )}
                      <ChatTranscript model={model} refs={refs} />
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
