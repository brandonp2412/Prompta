import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
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
    statuses,
    queueSnapshot,
    items,
    markingAllRead,
    drawerOpen,
    filtersOpen,
    search,
    statusFilter,
    loadingList,
    listError,
    pinned,
    visibleWaiting,
    unpinned,
    markAllRead,
    loadingMore,
    morePageFailed,
    nextOffset,
    total,
    loadMore,
    applyFilter,
    searchChanged,
    clearSearch,
    toggleSearch,
    showJobs,
    createChat,
  } = model;

  const [profileOpen, setProfileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const profileTriggerRef = useRef<HTMLButtonElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const settingsCloseRef = useRef<HTMLButtonElement>(null);
  const settingsSaveRef = useRef<HTMLButtonElement>(null);
  const settingsApprovalRef = useRef<HTMLInputElement>(null);
  const listEndRef = useRef<HTMLDivElement>(null);
  const [concurrency, setConcurrency] = useState({ enabled: true, max_workers: 3 });
  const [approval, setApproval] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [settingsReady, setSettingsReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const hasOlderChats = nextOffset.value < total.value;
  useEffect(() => {
    if (
      !hasOlderChats ||
      loadingList.value ||
      loadingMore.value ||
      morePageFailed.value ||
      typeof IntersectionObserver === "undefined"
    )
      return;
    const pane = model.listPane.peek();
    const end = listEndRef.current;
    if (!pane || !end) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadMore();
      },
      { root: pane, rootMargin: "200px 0px" },
    );
    observer.observe(end);
    return () => observer.disconnect();
  }, [hasOlderChats, loadingList.value, loadingMore.value, morePageFailed.value, nextOffset.value]);

  function onListScroll(event: React.UIEvent<HTMLDivElement>) {
    if (!hasOlderChats || loadingList.value || loadingMore.value || morePageFailed.value) return;
    const pane = event.currentTarget;
    if (pane.scrollHeight - pane.scrollTop - pane.clientHeight <= 200) void loadMore();
  }
  useEffect(() => {
    if (!profileOpen) return;
    const dismissOutside = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return;
      if (
        profileTriggerRef.current?.contains(event.target) ||
        profileMenuRef.current?.contains(event.target)
      )
        return;
      setProfileOpen(false);
    };
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setProfileOpen(false);
      profileTriggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissOnEscape);
    };
  }, [profileOpen]);
  useEffect(() => {
    if (!settingsOpen) return;
    settingsCloseRef.current?.focus();
    const handleKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setSettingsOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const lastControl = settingsSaveRef.current?.disabled
        ? settingsApprovalRef.current
        : settingsSaveRef.current;
      if (event.shiftKey && document.activeElement === settingsCloseRef.current) {
        event.preventDefault();
        lastControl?.focus();
      } else if (!event.shiftKey && document.activeElement === lastControl) {
        event.preventDefault();
        settingsCloseRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeys);
    return () => {
      document.removeEventListener("keydown", handleKeys);
      profileTriggerRef.current?.focus();
    };
  }, [settingsOpen]);
  useEffect(() => {
    if (!settingsOpen) return;
    const controller = new AbortController();
    setSettingsReady(false);
    void fetch("./api/settings", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load settings");
        return response.json();
      })
      .then((data) => {
        if (controller.signal.aborted) return;
        setConcurrency(data.stage_concurrency);
        setApproval(data.connector_approval.enabled);
        setSettingsError("");
        setSettingsReady(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setSettingsError("Could not load settings");
      });
    return () => controller.abort();
  }, [settingsOpen]);
  async function saveSettings() {
    setSaving(true);
    setSettingsError("");
    try {
      const response = await fetch("./api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage_concurrency: concurrency,
          connector_approval: { enabled: approval },
        }),
      });
      if (!response.ok) throw new Error("Settings could not be saved");
      setSettingsOpen(false);
    } catch {
      setSettingsError("Settings could not be saved");
    } finally {
      setSaving(false);
    }
  }

  function emptyChatsLabel() {
    if (listError.value) return "Chat list temporarily unavailable";
    if (search.value || statusFilter.value) return "No matching chats";
    return "No chats";
  }

  return (
    <aside aria-label="Local chat sidebar" ref={refs.sidebarPane} className="chats-sidebar">
      <div className="sidebar-topbar">
        <div className="sidebar-brand">
          <strong>Prompta</strong>
        </div>
        <nav aria-label="Main navigation" className="sidebar-actions">
          <button
            type="button"
            aria-label="Search chats"
            title="Search chats"
            aria-expanded={filtersOpen.value}
            aria-controls="chat-filters"
            onClick={toggleSearch}
            className="sidebar-search"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <circle cx="10.5" cy="10.5" r="6.5" />
              <path d="m16 16 5 5" />
            </svg>
            {(search.value || statusFilter.value) && (
              <span aria-label="Filters active" className="filter-active-dot" />
            )}
          </button>
        </nav>
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => (drawerOpen.value = false)}
          className="sidebar-close"
        >
          ×
        </button>
      </div>
      {filtersOpen.value ? (
        <>
          <div id="chat-filters" className="chats-controls">
            <div className="search-field">
              <label className="search-label">
                <span className="sr-only">Search chats</span>
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
              {search.value && (
                <button
                  type="button"
                  aria-label="Clear chat search"
                  title="Clear search"
                  className="chat-search-clear"
                  onClick={clearSearch}
                >
                  ×
                </button>
              )}
            </div>
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
      <div ref={refs.listPane} className="chats-list" onScroll={onListScroll}>
        {visibleWaiting.value.length ? (
          <>
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
        {hasOlderChats && morePageFailed.value ? (
          <button
            type="button"
            disabled={loadingList.value || loadingMore.value}
            onClick={() => void loadMore()}
            className="btn ghost"
          >
            Retry loading older chats
          </button>
        ) : null}
        {hasOlderChats && !morePageFailed.value && (
          <div ref={listEndRef} className="chat-list-end" aria-hidden="true" />
        )}
      </div>
      <div className="sidebar-footer">
        <button
          type="button"
          onClick={createChat}
          aria-label="New chat"
          title="New chat"
          className="sidebar-footer-new"
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
            <path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z" />
          </svg>
          <span>New chat</span>
        </button>
        <button
          type="button"
          aria-label="Profile"
          aria-expanded={profileOpen}
          aria-controls="sidebar-profile-menu"
          ref={profileTriggerRef}
          onClick={() => setProfileOpen(!profileOpen)}
          className="sidebar-profile"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21c0-5 16-5 16 0" />
          </svg>
          <span>Profile</span>
        </button>
        {profileOpen && (
          <div
            id="sidebar-profile-menu"
            ref={profileMenuRef}
            className="sidebar-profile-menu"
            role="group"
            aria-label="Profile actions"
          >
            <button
              type="button"
              onClick={() => {
                showJobs();
                setProfileOpen(false);
              }}
            >
              Jobs
            </button>
            <button
              type="button"
              onClick={() => {
                setSettingsReady(false);
                setSettingsOpen(true);
                setProfileOpen(false);
              }}
            >
              Settings
            </button>
            <button
              type="button"
              disabled={markingAllRead.value}
              onClick={() => {
                void markAllRead();
                setProfileOpen(false);
              }}
            >
              Mark all as read
            </button>
          </div>
        )}
      </div>
      {settingsOpen &&
        createPortal(
          <div className="settings-backdrop" onClick={() => setSettingsOpen(false)}>
            <section
              role="dialog"
              aria-modal="true"
              aria-label="Prompta settings"
              className="settings-dialog"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="settings-heading">
                <h2>Settings</h2>
                <button
                  type="button"
                  aria-label="Close settings"
                  ref={settingsCloseRef}
                  onClick={() => setSettingsOpen(false)}
                >
                  ×
                </button>
              </div>
              <h3>Concurrency</h3>
              <label className="settings-check">
                <input
                  type="checkbox"
                  checked={concurrency.enabled}
                  onChange={(event) =>
                    setConcurrency({ ...concurrency, enabled: event.target.checked })
                  }
                />{" "}
                Limit concurrent jobs and chats
              </label>
              <label className="settings-number">
                Maximum workers
                <input
                  type="number"
                  min="1"
                  max="128"
                  disabled={!concurrency.enabled}
                  value={concurrency.max_workers}
                  onChange={(event) =>
                    setConcurrency({ ...concurrency, max_workers: Number(event.target.value) })
                  }
                />
              </label>
              <p>
                One global limit for new chats, replies, one-off and repeating jobs. Running work is
                not interrupted.
              </p>
              <h3>Connector approval</h3>
              <label className="settings-check">
                <input
                  type="checkbox"
                  checked={approval}
                  ref={settingsApprovalRef}
                  onChange={(event) => setApproval(event.target.checked)}
                />{" "}
                Automatically approve trusted connector prompts
              </label>
              {settingsError && <p role="alert">{settingsError}</p>}
              <button
                type="button"
                className="settings-save"
                ref={settingsSaveRef}
                disabled={
                  !settingsReady ||
                  saving ||
                  (concurrency.enabled &&
                    (!Number.isInteger(concurrency.max_workers) ||
                      concurrency.max_workers < 1 ||
                      concurrency.max_workers > 128))
                }
                onClick={() => void saveSettings()}
              >
                {saving ? "Saving…" : "Save settings"}
              </button>
            </section>
          </div>,
          document.body,
        )}
    </aside>
  );
}
