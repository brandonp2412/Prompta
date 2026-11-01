import React, { useEffect, useLayoutEffect, useMemo, useState, useRef } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { createChatsPageController, type Props } from "./ChatsPageController";
import { chatUrl } from "./chatUrl";
import { canStopTurn, exactConversationUrl } from "./resultFormatting";
import JobsPage from "./JobsPage";
import ChatComposer from "./ChatComposer";
import ChatsSidebar from "./ChatsSidebar";
import ChatTranscript from "./ChatTranscript";
export default function ChatsPage(props: Props & { serverName: string }) {
  const model = useMemo(() => createChatsPageController(props), []);
  useSignals();
  const [shareNotice, setShareNotice] = useState("");
  const shareTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(shareTimer.current), []);
  async function shareChat() {
    const id = model.selectedRunId.peek();
    if (!id) return;
    clearTimeout(shareTimer.current);
    setShareNotice("");
    try {
      await navigator.clipboard.writeText(chatUrl(id));
      if (window.matchMedia("(min-width: 681px)").matches) setShareNotice("Chat link copied");
    } catch {
      setShareNotice("Could not copy chat link");
    }
    shareTimer.current = setTimeout(() => setShareNotice(""), 2500);
  }
  const {
    view,
    selectedRunId,
    newChatOpen,
    readError,
    drawerOpen,
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
  const pageTitle = view.value === "jobs" ? "Jobs" : selectedChatTitle.value;
  const conversationUrl =
    detail.value?.send_id === selectedRunId.value
      ? exactConversationUrl(
          turns.value.findLast((turn) => exactConversationUrl(turn.conversation_id))
            ?.conversation_id || detail.value.conversation_id,
        )
      : null;
  const latestSelectedTurn =
    selectedRunId.value && detail.value?.send_id === selectedRunId.value
      ? turns.value.findLast((turn) => turn.status !== "cancelled")
      : undefined;
  const activeSelectedChat = canStopTurn(latestSelectedTurn);
  useEffect(() => {
    document.title = `Prompta · ${pageTitle} · ${props.serverName}`;
  }, [pageTitle, props.serverName]);
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
    window.addEventListener("touchmove", model.moveSwipe, { passive: false });
    window.addEventListener("touchend", finishSwipe);
    window.addEventListener("touchcancel", cancelSwipe);
    return () => {
      window.removeEventListener("keydown", escapeDrawer);
      window.removeEventListener("touchstart", startSwipe);
      window.removeEventListener("touchmove", model.moveSwipe);
      window.removeEventListener("touchend", finishSwipe);
      window.removeEventListener("touchcancel", cancelSwipe);
    };
  }, [model]);
  return (
    <>
      {shareNotice && (
        <div className="share-toast" role="status">
          {shareNotice}
        </div>
      )}
      <DrawerLayout model={model}>
        <button
          type="button"
          aria-label="Close chat sidebar"
          tabIndex={drawerOpen.value ? 0 : -1}
          onClick={() => (drawerOpen.value = false)}
          className="drawer-backdrop"
        ></button>
        <ChatsSidebar model={model} refs={refs} />

        <div className="chats-detail">
          {model.stopError.value && (
            <p role="alert" className="result-error">
              {model.stopError.value}
            </p>
          )}
          <div className="workspace-header">
            <button
              type="button"
              aria-label="Open chat sidebar"
              aria-expanded={drawerOpen.value}
              onClick={() => (drawerOpen.value = true)}
              className="sidebar-menu"
            >
              ☰
            </button>
            <strong>{view.value === "jobs" ? "Jobs" : selectedChatTitle.value}</strong>
            {view.value === "chats" && selectedRunId.value && (
              <button
                type="button"
                className="chat-share"
                aria-label="Share chat"
                title="Copy chat link"
                onClick={() => void shareChat()}
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
                  <path d="M12 16V3m-5 5 5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
                </svg>
              </button>
            )}
            {view.value === "chats" && selectedRunId.value && conversationUrl && (
              <a
                className="chat-open-chatgpt"
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
                active={activeSelectedChat}
                stopping={model.stopping.value === selectedRunId.value}
                onStop={() => {
                  const id = selectedRunId.value;
                  if (id) return model.stopJob(id);
                }}
                onSend={selectedRunId.value ? sendReply : sendFresh}
                onFallbackSend={(text) =>
                  sendFresh(freshContinuationPrompt(text), originalImageRefs())
                }
                offerFreshContinuation={Boolean(
                  selectedRunId.value &&
                  detail.value?.send_id === selectedRunId.value &&
                  !detail.value.conversation_id &&
                  !turns.value.at(-1)?.conversation_id &&
                  ["completed", "interrupted", "unavailable", "outcome_unknown"].includes(
                    turns.value.at(-1)?.status ?? "",
                  ),
                )}
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
      </DrawerLayout>
    </>
  );
}

function DrawerLayout({
  model,
  children,
}: {
  model: ReturnType<typeof createChatsPageController>;
  children: React.ReactNode;
}) {
  useSignals();
  const progress = model.visibleDrawerProgress.value;
  return (
    <section
      aria-label="Prompta local chats and jobs"
      className={[
        "chats-layout",
        model.drawerOpen.value ? "drawer-open" : "",
        model.drawerProgress.value !== null ? "drawer-interacting" : "",
        model.view.value === "chats" && !model.selectedRunId.value && !model.newChatOpen.value
          ? "show-list"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={
        {
          "--drawer-offset": `${(progress - 1) * 100}%`,
          "--drawer-opacity": progress * 0.6,
        } as React.CSSProperties
      }
    >
      {children}
    </section>
  );
}
