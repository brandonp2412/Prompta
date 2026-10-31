import React from "react";
import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import ChatRow from "./ChatRow";
import { queueEtaExplanation, queueEtaText } from "./queueStatus";
import type { ChatListStatus } from "./resultFormatting";

type SidebarRefs = {
  sidebarPane: (element: HTMLElement | null) => void;
  searchInput: (element: HTMLInputElement | null) => void;
  listPane: (element: HTMLDivElement | null) => void;
};

export default function ChatsSidebar({
  model,
  refs,
}: {
  model: ReturnType<typeof createChatsPageController>;
  refs: SidebarRefs;
}) {
  useSignals();
  const {
    retryPins,
    view,
    selectedRunId,
    statuses,
    queueSnapshot,
    queueError,
    items,
    pinError,
    readError,
    markingAllRead,
    attentionChats,
    drawerOpen,
    filtersOpen,
    search,
    statusFilter,
    loadingList,
    listError,
    morePageFailed,
    pinned,
    visibleWaiting,
    unpinned,
    retryReadSync,
    markAllRead,
    loadQueue,
    maybeLoadMore,
    loadList,
    loadMore,
    applyFilter,
    searchChanged,
    toggleSearch,
    showJobs,
    createChat,
  } = model;

  function emptyChatsLabel() {
    if (listError.value) return "Chat list temporarily unavailable";
    if (search.value || statusFilter.value) return "No matching chats";
    return "No chats";
  }

  const attentionCount = attentionChats.value ?? 0;

  return (
    <aside aria-label="Local chat sidebar" ref={refs.sidebarPane} className="chats-sidebar">
      <div className="sidebar-brand">
        <div>
          <strong>Prompta</strong>
        </div>
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => (drawerOpen.value = false)}
          className="sidebar-close"
        >
          ×
        </button>
      </div>
      <nav aria-label="Main navigation" className="sidebar-actions">
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
          <span className="action-label">Jobs</span>
        </button>
        <button
          type="button"
          onClick={createChat}
          aria-label="New chat"
          title="New chat"
          className="sidebar-primary"
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
          <span className="action-label">New</span>
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
          <span className="action-label">Search</span>
          {search.value || statusFilter.value ? (
            <>
              <span aria-label="Filters active" className="filter-active-dot"></span>
            </>
          ) : (
            <></>
          )}
        </button>
      </nav>
      <div className="sidebar-read-actions">
        <button
          type="button"
          onClick={markAllRead}
          disabled={markingAllRead.value}
          aria-label="Mark all local chats as read"
          title="Mark all local chats as read"
          className="mark-all-read"
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
      {attentionCount > 0 && (
        <button
          type="button"
          className="chat-attention-shortcut"
          title="Review failed or interrupted local captures"
          onClick={() => {
            search.value = "";
            statusFilter.value = "needs_attention";
            filtersOpen.value = true;
            applyFilter();
          }}
        >
          <span>Needs attention</span>
          <strong>
            {attentionCount} {attentionCount === 1 ? "chat" : "chats"}
          </strong>
        </button>
      )}
      {filtersOpen.value ? (
        <>
          <div id="chat-filters" className="chats-controls">
            <label className="search-label">
              <span className="sr-only">Search job results</span>
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
              <span className="sr-only">Filter results by state</span>
              <select
                value={statusFilter.value}
                onChange={(event) => {
                  statusFilter.value = event.currentTarget.value as ChatListStatus;
                  applyFilter();
                }}
              >
                {statuses.map((choice) => (
                  <option key={choice.value} value={choice.value}>
                    {choice.label}
                  </option>
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
          <div role="alert" className="result-error recovery-error">
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
          <div role="alert" className="result-error recovery-error">
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
          <div role="alert" className="result-error recovery-error">
            <span>{pinError.value}</span>
            <button type="button" onClick={retryPins}>
              Retry pins
            </button>
          </div>
        </>
      ) : (
        <></>
      )}
      {readError.value && (view.value !== "chats" || !selectedRunId.value) ? (
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
      <div ref={refs.listPane} onScroll={maybeLoadMore} className="chats-list">
        {visibleWaiting.value.length ? (
          <>
            <div aria-live="polite" className="chats-date queue-heading">
              <span>Waiting to start · {visibleWaiting.value.length}</span>
              <span>
                {queueSnapshot.value.max_workers === null
                  ? "Stage capacity"
                  : `${queueSnapshot.value.occupied_slots}/${queueSnapshot.value.max_workers} global slots`}
              </span>
            </div>
            {visibleWaiting.value.map((waiting) => (
              <div key={waiting.name} className="chat-entry queue-waiting">
                <button
                  type="button"
                  onClick={showJobs}
                  title={"Open Jobs for " + waiting.name}
                  className="chat-row"
                >
                  <span className="chat-row-top">
                    <strong>{waiting.name}</strong>
                    <span className="queue-position">
                      #{waiting.position} of {queueSnapshot.value.waiting.length}
                    </span>
                  </span>
                  <span className="queue-subtitle" title={queueEtaExplanation(queueSnapshot.value)}>
                    {queueEtaText(waiting)} · {waiting.reason === "stage" ? "stage" : "global"}{" "}
                    limit ({waiting.occupied}/{waiting.limit})
                  </span>
                </button>
              </div>
            ))}
          </>
        ) : (
          <></>
        )}
        {pinned.value.length ? (
          <>
            {pinned.value.map((item) => (
              <ChatRow key={item.send_id} item={item} model={model} />
            ))}
          </>
        ) : (
          <></>
        )}
        {loadingList.value && !items.value.length && !pinned.value.length ? (
          <>
            <p className="chats-empty">Loading chats…</p>
          </>
        ) : (
          <>
            {!items.value.length && !pinned.value.length && !visibleWaiting.value.length ? (
              <>
                <p className="chats-empty">{emptyChatsLabel()}</p>
              </>
            ) : (
              <>
                {unpinned.value.map((item) => (
                  <ChatRow key={item.send_id} item={item} model={model} />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
