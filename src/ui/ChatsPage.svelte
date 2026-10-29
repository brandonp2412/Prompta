<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import JobsPage from "./JobsPage.svelte";
  import ChatComposer from "./ChatComposer.svelte";
  import ResultMarkdown from "./ResultMarkdown.svelte";
  import ToolCalls from "./ToolCalls.svelte";
  import { subscribeLiveUpdates } from "./liveUpdates";
  import {
    formatStoredResponse, nzTime, statusLabel, turnStatus,
    type LocalTurn, type ResultStatus, type RunDetail, type RunSummary,
  } from "./resultFormatting";

  let { view, selectedRunId, newChatOpen, onSelect, onNavigate, onNewChat, onQueued }: {
    view: "jobs" | "chats";
     selectedRunId: string | null;
    newChatOpen: boolean;
    onSelect: (sendId: string | null) => void;
    onNavigate: (view: "jobs" | "chats") => void;
    onNewChat: () => void;
    onQueued: (sendId: string) => void;
  } = $props();

  const pageSize = 20;
  const preferencesKey = "prompta.local-sidebar.v1";
  const statuses: { value: ResultStatus | ""; label: string }[] = [
    { value: "", label: "All states" },
    { value: "accepted", label: "Accepted" },
    { value: "generating", label: "Generating" },
    { value: "completed", label: "Completed" },
    { value: "interrupted", label: "Interrupted" },
    { value: "unavailable", label: "Unavailable" },
    { value: "queued", label: "Queued" },
  ];

  type WaitingJob = { name: string; position: number; reason: "global" | "stage"; occupied: number; limit: number };
  type QueueSnapshot = { max_workers: number | null; occupied_slots: number; waiting: WaitingJob[] };
  let queueSnapshot = $state<QueueSnapshot>({ max_workers: null, occupied_slots: 0, waiting: [] });
  let queueGeneration = 0;
  let queuePollTimer: ReturnType<typeof setInterval> | undefined;
  let detailPollTimer: ReturnType<typeof setInterval> | undefined;
  let items = $state<RunSummary[]>([]);
  let pinnedItems = $state<RunSummary[]>([]);
  let pinnedIds = $state<string[]>([]);
  let legacyPinIds: string[] = [];
  let confirmedPins: RunSummary[] = [];
  let pinsReady = $state(false);
  let pendingPinWrites = 0;
  let pinWriteQueue: Promise<void> = Promise.resolve();
  let pinError = $state("");
  let readAt = $state<Record<string, number>>({});
  let readRevisions = $state<Record<string, string>>({});
  let baselineAt = $state(0);
  let drawerOpen = $state(false);
  let filtersOpen = $state(false);
  let expandedPrompts = $state<Record<string, boolean>>({});
  let total = $state(0);
  let nextOffset = $state(0);
  let loadingMore = $state(false);
  let search = $state("");
  let statusFilter = $state<ResultStatus | "">("");
  let detail = $state<RunDetail | null>(null);
  let turns = $state<LocalTurn[]>([]);
  let turnsError = $state("");
  let recoveringReply = $state(false);
  let copyState = $state("");
  let scrollPane = $state<HTMLDivElement>();
  let listPane = $state<HTMLDivElement>();
  let searchInput = $state<HTMLInputElement>();
  let loadingList = $state(true);
  let loadingDetail = $state(false);
  let listError = $state("");
  let detailError = $state("");
  let listGeneration = 0;
  let pinsGeneration = 0;
  let detailGeneration = 0;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let liveRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let swipeStart: { x: number; y: number; opening: boolean } | null = null;

  const activity = (item: RunSummary) => item.updated_at || item.created_at;
  const newestFirst = (a: RunSummary, b: RunSummary) =>
    activity(b) - activity(a) || b.created_at - a.created_at || a.send_id.localeCompare(b.send_id);
  let pinned = $derived.by(() => {
    // Pinned runs remain available when they fall outside the current local page.
    const byId = new Map([...pinnedItems, ...items].map((item) => [item.send_id, item]));
    const filtered = search.trim() || statusFilter;
    return pinnedIds
      .map((id) => byId.get(id))
      .filter((item): item is RunSummary => !!item)
      .filter((item) => !filtered || items.some((listed) => listed.send_id === item.send_id));
  });
  const replyBlockedReason = $derived.by((): string => {
    const latest = turns.at(-1);
    if (!detail || !latest) return "Loading reply availability…";
    if (latest.status === "prepared" || latest.status === "preflight_failed") {
      return latest.reply_id && latest.conversation_id && latest.parent_id
        ? "" : "The saved reply has no verified target, so it cannot be resent.";
    }
    if (latest.status === "completed") {
      if (!latest.conversation_id) {
        return "This chat was saved without its ChatGPT conversation ID, so it cannot be safely replied to.";
      }
      if (turns.length > 1 && !latest.message_id) {
        return "The latest assistant reply has no verified message ID. This branch cannot be safely continued.";
      }
      return "";
    }
    if (latest.status === "outcome_unknown") {
      return "The last reply may have been sent. Check ChatGPT before trying anything else.";
    }
    if (latest.status === "interrupted" || latest.status === "unavailable") {
      return "The last response did not finish reliably, so a same-branch reply is unavailable.";
    }
    return "You can reply when this chat has a completed response.";
  });
  let visibleWaiting = $derived(
    statusFilter && statusFilter !== "queued" ? [] :
      queueSnapshot.waiting.filter((job) =>
        !search.trim() || job.name.toLowerCase().includes(search.trim().toLowerCase())
      )
  );
  let unpinned = $derived(items.filter((item) => !pinnedIds.includes(item.send_id)).sort(newestFirst));

  function loadPreferences() {
    try {
      const saved = localStorage.getItem(preferencesKey);
      if (saved) {
        const prefs: { baselineAt?: number; pinnedIds?: string[]; readAt?: Record<string, number>; readRevisions?: Record<string, string> } = JSON.parse(saved);
        baselineAt = Number.isFinite(prefs.baselineAt) ? Number(prefs.baselineAt) : Date.now() / 1000;
        legacyPinIds = Array.isArray(prefs.pinnedIds) ? prefs.pinnedIds.filter((id) => typeof id === "string").slice(0, 24) : [];
        readAt = prefs.readAt && typeof prefs.readAt === "object" ? prefs.readAt : {};
        readRevisions = prefs.readRevisions && typeof prefs.readRevisions === "object" ? prefs.readRevisions : {};
      } else baselineAt = Date.now() / 1000;
    } catch {
      baselineAt = Date.now() / 1000;
    }
    savePreferences();
  }

  function savePreferences() {
    try {
      // Only opaque local send IDs and timestamps are stored, never chat content.
      const recent = Object.entries(readAt).sort((a, b) => b[1] - a[1]).slice(0, 2000);
      const recentIds = new Set(recent.map(([id]) => id));
      localStorage.setItem(preferencesKey, JSON.stringify({
        baselineAt, readAt: Object.fromEntries(recent),
        ...(legacyPinIds.length ? { pinnedIds: legacyPinIds } : {}),
        readRevisions: Object.fromEntries(Object.entries(readRevisions).filter(([id]) => recentIds.has(id))),
      }));
    } catch {
      // Private browsing and disabled storage still allow in-memory navigation.
    }
  }

  function isUnread(item: RunSummary) {
    if (!item.last_reply_revision) return false;
    const seenRevision = readRevisions[item.send_id];
    if (seenRevision) return seenRevision !== item.last_reply_revision;
    // Existing timestamp-only read preferences migrate without false alerts.
    return item.last_reply_at > (readAt[item.send_id] ?? baselineAt);
  }

  function markRead(item: RunSummary) {
    readAt = { ...readAt, [item.send_id]: Math.max(Date.now() / 1000, activity(item)) };
    if (item.last_reply_revision) {
      readRevisions = { ...readRevisions, [item.send_id]: item.last_reply_revision };
    }
    savePreferences();
  }

  async function loadPins() {
    const generation = ++pinsGeneration;
    if (pendingPinWrites) return;
    try {
      if (legacyPinIds.length) {
        const imported = await fetch("./api/local-chat-pins/import", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ send_ids: legacyPinIds }),
        });
        if (!imported.ok) throw new Error("Local pin import failed");
        legacyPinIds = [];
        savePreferences();
      }
      const response = await fetch("./api/local-chat-pins", { cache: "no-store" });
      if (!response.ok) throw new Error("Local pins unavailable");
      const body: { items: RunSummary[] } = await response.json();
      if (generation !== pinsGeneration || pendingPinWrites) return;
      confirmedPins = body.items;
      pinnedItems = body.items;
      pinnedIds = body.items.map((item) => item.send_id);
      pinsReady = true;
    } catch {
      if (generation === pinsGeneration) pinError = "Pinned chats are temporarily unavailable.";
    }
  }

  function togglePin(item: RunSummary) {
    if (!pinsReady) return;
    const next = !pinnedIds.includes(item.send_id);
    pinsGeneration += 1; // Ignore older GETs while an explicit change is pending.
    pinError = "";
    if (next) {
      pinnedIds = [item.send_id, ...pinnedIds];
      pinnedItems = [item, ...pinnedItems.filter((pinnedItem) => pinnedItem.send_id !== item.send_id)];
    } else {
      pinnedIds = pinnedIds.filter((id) => id !== item.send_id);
      pinnedItems = pinnedItems.filter((pinnedItem) => pinnedItem.send_id !== item.send_id);
    }
    pendingPinWrites += 1;
    // Serialize requests so rapid pin/unpin operations reach SQLite in click order.
    pinWriteQueue = pinWriteQueue.then(async () => {
      try {
        const response = await fetch("./api/local-chat-pins", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ send_id: item.send_id, pinned: next }),
        });
        if (!response.ok) throw new Error("Local pin update failed");
        confirmedPins = next
          ? [item, ...confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id)]
          : confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id);
      } catch {
        pinError = "Could not save pinned chat.";
      } finally {
        pendingPinWrites -= 1;
        if (!pendingPinWrites) {
          // A failed request must not leave a phantom optimistic pin on screen.
          pinnedItems = confirmedPins;
          pinnedIds = confirmedPins.map((confirmed) => confirmed.send_id);
          void loadPins();
        }
      }
    });
  }

  async function loadQueue() {
    const generation = ++queueGeneration;
    try {
      const response = await fetch("./api/queue-status", { cache: "no-store" });
      if (!response.ok) return;
      const body: QueueSnapshot = await response.json();
      if (generation === queueGeneration) queueSnapshot = body;
    } catch {
      // Keep the last confirmed snapshot through a transient local outage.
    }
  }

  function resultsParams(offset: number) {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
    if (search.trim()) params.set("q", search.trim());
    if (statusFilter) params.set("status", statusFilter);
    return params;
  }

  function mergeRuns(previous: RunSummary[], incoming: RunSummary[]) {
    return [...new Map([...previous, ...incoming].map((item) => [item.send_id, item])).values()].sort(newestFirst);
  }

  function maybeLoadMore() {
    if (loadingList || loadingMore || nextOffset >= total || !listPane) return;
    if (listPane.scrollTop + listPane.clientHeight >= listPane.scrollHeight - 240) void loadMore();
  }

  async function loadList(reset = false) {
    const generation = ++listGeneration;
    loadingMore = false; // A fresh first-page response supersedes an in-flight append.
    if (reset) {
      items = [];
      total = 0;
      nextOffset = 0;
      if (listPane) listPane.scrollTop = 0;
    }
    loadingList = items.length === 0;
    try {
      const response = await fetch("./api/results?" + resultsParams(0), { cache: "no-store" });
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      items = reset ? body.items : mergeRuns(items, body.items);
      total = body.total;
      nextOffset = Math.max(nextOffset, body.items.length);
      listError = "";
    } catch {
      if (generation === listGeneration) listError = "Local results are temporarily unavailable.";
    } finally {
      if (generation === listGeneration) {
        loadingList = false;
        await tick();
        maybeLoadMore();
      }
    }
  }

  async function loadMore() {
    if (loadingMore || loadingList || nextOffset >= total) return;
    const generation = listGeneration;
    const offset = nextOffset;
    loadingMore = true;
    try {
      const response = await fetch("./api/results?" + resultsParams(offset), { cache: "no-store" });
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      items = mergeRuns(items, body.items);
      total = body.total;
      nextOffset = offset + body.items.length;
      listError = "";
    } catch {
      if (generation === listGeneration) listError = "More local chats could not be loaded.";
    } finally {
      if (generation === listGeneration) {
        loadingMore = false;
        await tick();
        // On a tall viewport, continue until the rail actually overflows.
        if (!listError) maybeLoadMore();
      }
    }
  }

  async function loadDetail(id: string) {
    const generation = ++detailGeneration;
    const newSelection = detail?.send_id !== id;
    if (newSelection) { detail = null; turns = []; }
    const followTail = newSelection || !!scrollPane &&
      scrollPane.scrollHeight - scrollPane.scrollTop - scrollPane.clientHeight < 96;
    loadingDetail = true;
    try {
      const path = "./api/results/" + encodeURIComponent(id);
      const [response, replyResponse] = await Promise.all([
        fetch(path, { cache: "no-store" }),
        fetch(path + "/turns", { cache: "no-store" }),
      ]);
      if (!response.ok) throw new Error("Result not found");
      const body: RunDetail = await response.json();
      const saved = replyResponse.ok ? await replyResponse.json() as { turns: LocalTurn[] } : null;
      if (generation !== detailGeneration) return;
      detail = body;
      turns = saved?.turns?.length ? saved.turns : [{
        reply_id: "", user_text: body.user_text, assistant_text: body.assistant_text,
        tool_calls: body.tool_calls,
        status: body.status, created_at: body.created_at, updated_at: body.updated_at,
      }];
      turnsError = !replyResponse.ok ? "Saved replies are temporarily unavailable locally." : "";
      detailError = "";
      if (view === "chats" && selectedRunId === id) markRead(body);
      await tick();
      if (followTail && scrollPane && selectedRunId === id) scrollPane.scrollTop = scrollPane.scrollHeight;
    } catch {
      if (generation === detailGeneration) detailError = "This run is unavailable locally.";
    } finally {
      if (generation === detailGeneration) loadingDetail = false;
    }
  }

  async function sendFresh(text: string, images: string[]) {
    const requestId = crypto.randomUUID().replaceAll("-", "");
    try {
      const response = await fetch("./api/chats", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ request_id: requestId, prompt: text, images }),
      });
      if (!response.ok) {
        return {
          ok: false, ambiguous: response.status >= 500,
          message: response.status >= 500
            ? "The queue result is uncertain. Check local Chats; no automatic resend."
            : "The fresh chat was rejected. Review the prompt or images.",
        };
      }
      const body = await response.json() as { send_id?: string };
      if (!body.send_id) throw new Error("Missing queue receipt");
      // The queue has already persisted this run locally. Show it as soon as
      // the receipt is confirmed, even if the previous list was filtered.
      search = "";
      statusFilter = "";
      onQueued(body.send_id);
      void loadList(true);
      void loadPins();
      return { ok: true, message: "" };
    } catch {
      return {
        ok: false, ambiguous: true,
        message: "Queue confirmation was lost. Check local Chats before another explicit send; no automatic retry.",
      };
    }
  }

  async function recoverReply(sendId: string): Promise<string> {
    if (recoveringReply) return "";
    recoveringReply = true;
    try {
      // A Send click is the explicit user action that permits exact-branch
      // verification. Opening or refreshing a chat never contacts ChatGPT.
      const response = await fetch(
        "./api/results/" + encodeURIComponent(sendId) + "/reply-recover",
        { method: "POST", headers: { "content-type": "application/json" }, body: "{}" },
      );
      if (!response.ok) return "";
      const recovered = await response.json() as { message_id?: string };
      return selectedRunId === sendId ? recovered.message_id ?? "" : "";
    } catch {
      return "";
    } finally {
      recoveringReply = false;
    }
  }

  async function sendReply(text: string, _images: string[]) {
    const sendId = selectedRunId;
    const latest = turns.at(-1);
    if (sendId && (latest?.status === "prepared" || latest?.status === "preflight_failed")) {
      if (!latest.reply_id || !latest.conversation_id || !latest.parent_id || text !== latest.user_text) {
        return { ok: false, message: "A pending reply can only be retried with its original text." };
      }
      return sendExactReply(sendId, {
        reply_id: latest.reply_id,
        conversation_id: latest.conversation_id,
        parent_id: latest.parent_id,
        text: latest.user_text,
      });
    }
    if (!sendId || latest?.status !== "completed") {
      return { ok: false, message: "Wait for the current response to finish." };
    }
    if (!latest.conversation_id) {
      return { ok: false, message: "This chat has no verified reply branch." };
    }
    const parentId = latest.message_id || (turns.length === 1 ? await recoverReply(sendId) : "");
    if (!parentId) {
      return { ok: false, message: "The reply branch could not be verified. Nothing was sent." };
    }
    if (selectedRunId !== sendId) {
      return { ok: false, message: "The selected chat changed. Nothing was sent." };
    }
    return sendExactReply(sendId, {
      reply_id: crypto.randomUUID().replaceAll("-", ""),
      conversation_id: latest.conversation_id,
      parent_id: parentId,
      text,
    });
  }

  async function sendExactReply(sendId: string, payload: {
    reply_id: string; conversation_id: string; parent_id: string; text: string;
  }) {
    try {
      const response = await fetch("./api/results/" + encodeURIComponent(sendId) + "/reply-send", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const problem = response.status < 500
          ? await response.json().catch(() => null) as { error?: string } | null : null;
        return {
          ok: false, ambiguous: response.status >= 500,
          message: response.status >= 500
            ? "Reply outcome could not be confirmed. Check local turns; do not resubmit blindly."
            : problem?.error || "Reply was not queued. Check the account-wide send gap and saved branch.",
        };
      }
      await loadDetail(sendId);
      return { ok: true, message: "" };
    } catch {
      return {
        ok: false, ambiguous: true,
        message: "Reply acknowledgment was lost. Check local turns; no automatic retry.",
      };
    }
  }

  async function copyText(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      copyState = key;
    } catch {
      copyState = "error:" + key;
    }
  }

  function refresh() {
    void loadQueue();
    void loadList();
    void loadPins();
    if (view === "chats" && selectedRunId) void loadDetail(selectedRunId);
  }

  function applyFilter() {
    void loadList(true);
  }

  function searchChanged() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilter, 300);
  }

  async function toggleSearch() {
    filtersOpen = !filtersOpen;
    if (filtersOpen) {
      await tick();
      searchInput?.focus();
    }
  }

  function startSwipe(event: TouchEvent) {
    if (!window.matchMedia("(max-width: 680px)").matches || event.touches.length !== 1) return;
    const touch = event.touches[0];
    const showList = view === "chats" && !selectedRunId && !newChatOpen;
    if (drawerOpen || (!showList && touch.clientX <= 120)) {
      swipeStart = { x: touch.clientX, y: touch.clientY, opening: !drawerOpen };
    }
  }

  function finishSwipe(event: TouchEvent) {
    if (!swipeStart || event.changedTouches.length !== 1) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - swipeStart.x;
    const dy = touch.clientY - swipeStart.y;
    if (Math.abs(dx) >= 64 && Math.abs(dx) > Math.abs(dy) * 1.25) {
      if (swipeStart.opening && dx > 0) drawerOpen = true;
      else if (!swipeStart.opening && dx < 0) drawerOpen = false;
    }
    swipeStart = null;
  }

  function selectRun(item: RunSummary) {
    markRead(item);
    drawerOpen = false;
    onSelect(item.send_id);
  }

  function showJobs() {
    drawerOpen = false;
    onNavigate("jobs");
  }

  function showChats() {
    drawerOpen = false;
    onSelect(null);
  }

  function createChat() {
    drawerOpen = false;
    onNewChat();
  }

  function escapeDrawer(event: KeyboardEvent) {
    if (event.key === "Escape" && drawerOpen) drawerOpen = false;
  }

  async function togglePrompt(key: string, event: MouseEvent) {
    const bubble = (event.currentTarget as HTMLElement).closest(".prompt-bubble");
    const originalTop = bubble?.getBoundingClientRect().top;
    expandedPrompts = { ...expandedPrompts, [key]: !expandedPrompts[key] };
    await tick();
    // Keep the start of the bubble in place instead of letting scroll anchoring grow it upward.
    if (bubble && scrollPane && originalTop !== undefined) {
      scrollPane.scrollTop += bubble.getBoundingClientRect().top - originalTop;
    }
  }

  $effect(() => {
    const id = view === "chats" ? selectedRunId : null;
    untrack(() => {
      if (id) void loadDetail(id);
      else {
        detailGeneration += 1;
        detail = null;
        turns = [];
        turnsError = "";
        detailError = "";
      }
    });
  });

  onMount(() => {
    loadPreferences();
    void loadList();
    void loadPins();
    void loadQueue();
    queuePollTimer = setInterval(() => { if (document.visibilityState === "visible") void loadQueue(); }, 15000);
    // Poll only Prompta's local turn record while an explicit reply is active.
    // This never opens ChatGPT or submits another message.
    detailPollTimer = setInterval(() => {
      if (document.visibilityState !== "visible" || view !== "chats" || !selectedRunId) return;
      if (["prepared", "dispatching", "accepted", "generating"].includes(turns.at(-1)?.status ?? "")) {
        void loadDetail(selectedRunId);
      }
    }, 5000);
    const unsubscribeJobs = subscribeLiveUpdates("jobs", () => void loadQueue());
    const unsubscribe = subscribeLiveUpdates("chats", () => {
      clearTimeout(liveRefreshTimer);
      liveRefreshTimer = setTimeout(refresh, 100);
    });
    return () => {
      unsubscribe();
      unsubscribeJobs();
      clearInterval(queuePollTimer);
      clearInterval(detailPollTimer);
      clearTimeout(liveRefreshTimer);
      clearTimeout(searchTimer);
    };
  });
</script>

<svelte:window onkeydown={escapeDrawer} ontouchstart={startSwipe} ontouchend={finishSwipe} ontouchcancel={() => swipeStart = null} />

{#snippet chatItem(item: RunSummary)}
  <div class:chosen={view === "chats" && selectedRunId === item.send_id} class:unread={isUnread(item)} class="chat-entry">
    <button
      type="button"
      class="chat-row"
      onclick={() => selectRun(item)}
      aria-current={view === "chats" && selectedRunId === item.send_id ? "true" : undefined}
    >
      <span class="chat-row-top">
        {#if isUnread(item)}<span class="unread-indicator" title="Unread reply"><span class="sr-only">Unread reply</span></span>{/if}
        <strong>{item.title || "Untitled run"}</strong>
        <span class={"result-dot status-" + item.status} title={statusLabel(item.status)}><span class="sr-only">{statusLabel(item.status)}</span></span>
      </span>
    </button>
    <button
      type="button" disabled={!pinsReady} class:active={pinnedIds.includes(item.send_id)} class="chat-pin"
      title={pinnedIds.includes(item.send_id) ? "Unpin local chat" : "Pin local chat"}
      aria-label={pinnedIds.includes(item.send_id) ? "Unpin " + item.title : "Pin " + item.title}
      aria-pressed={pinnedIds.includes(item.send_id)}
      onclick={() => togglePin(item)}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7" /></svg>
    </button>
  </div>
{/snippet}

<section class:drawer-open={drawerOpen} class:show-list={view === "chats" && !selectedRunId && !newChatOpen} class="chats-layout" aria-label="Prompta local chats and jobs">
  {#if drawerOpen}
    <button type="button" class="drawer-backdrop" aria-label="Close chat sidebar" onclick={() => drawerOpen = false}></button>
  {/if}
  <aside class="chats-sidebar" aria-label="Local chat sidebar">
    <div class="sidebar-brand">
      <div><strong>Prompta</strong></div>
      <button class="sidebar-close" type="button" aria-label="Close sidebar" onclick={() => drawerOpen = false}>×</button>
    </div>
    <nav class="sidebar-actions" aria-label="Main navigation">
      <button class:active={view === "jobs"} class="sidebar-jobs" type="button" onclick={showJobs} aria-label="Jobs" title="Jobs" aria-current={view === "jobs" ? "page" : undefined}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 9h8M8 13h8M8 17h5" /></svg>
        <span class="action-label">Jobs</span>
      </button>
      <button class="sidebar-primary" type="button" onclick={createChat} aria-label="New chat" title="New chat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z" /></svg>
        <span class="action-label">New</span>
      </button>
      <button class:active={filtersOpen} class="sidebar-search" type="button" aria-label="Search chats" title="Search chats" aria-expanded={filtersOpen} aria-controls="chat-filters" onclick={toggleSearch}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
        <span class="action-label">Search</span>
        {#if search || statusFilter}<span class="filter-active-dot" aria-label="Filters active"></span>{/if}
      </button>
    </nav>
    {#if filtersOpen}
    <div id="chat-filters" class="chats-controls">
      <label class="search-label">
        <span class="sr-only">Search job results</span>
        <input type="search" placeholder="Search chats" bind:this={searchInput} bind:value={search} oninput={searchChanged} />
      </label>
      <label>
        <span class="sr-only">Filter results by state</span>
        <select bind:value={statusFilter} onchange={applyFilter}>
          {#each statuses as choice}<option value={choice.value}>{choice.label}</option>{/each}
        </select>
      </label>
    </div>
    {/if}
    {#if listError}<div class="result-error" role="alert">{listError}</div>{/if}
    {#if pinError}<div class="result-error" role="alert">{pinError}</div>{/if}
    <div class="chats-list" bind:this={listPane} onscroll={maybeLoadMore}>
      {#if visibleWaiting.length}
        <div class="chats-date queue-heading" aria-live="polite">
          <span>Waiting to start · {visibleWaiting.length}</span>
          <span>{queueSnapshot.max_workers === null ? "Stage capacity" : `${queueSnapshot.occupied_slots}/${queueSnapshot.max_workers} global slots`}</span>
        </div>
        {#each visibleWaiting as waiting (waiting.name)}
          <div class="chat-entry queue-waiting">
            <button type="button" class="chat-row" onclick={showJobs} title={"Open Jobs for " + waiting.name}>
              <span class="chat-row-top"><strong>{waiting.name}</strong><span class="queue-position">#{waiting.position}</span></span>
              <span class="queue-subtitle">Queued · {waiting.reason === "stage" ? "stage" : "global"} limit ({waiting.occupied}/{waiting.limit})</span>
            </button>
          </div>
        {/each}
      {/if}
      {#if pinned.length}
        {#each pinned as item (item.send_id)}{@render chatItem(item)}{/each}
      {/if}
      {#if loadingList && !items.length}
        <p class="chats-empty">Loading chats…</p>
      {:else if !items.length && !pinned.length && !visibleWaiting.length}
        <p class="chats-empty">{search || statusFilter ? "No matching chats" : "No chats"}</p>
      {:else}
        {#each unpinned as item (item.send_id)}{@render chatItem(item)}{/each}
      {/if}
    </div>
  </aside>

  <div class="chats-detail">
    <div class="workspace-header">
      <button class="sidebar-menu" type="button" aria-label="Open chat sidebar" aria-expanded={drawerOpen} onclick={() => drawerOpen = true}>☰</button>
      <strong>{view === "jobs" ? "Jobs" : (detail?.title || detail?.job_name || "Chats")}</strong>
    </div>
    {#if view === "jobs"}
      <div class="jobs-workspace"><JobsPage /></div>
    {:else if !selectedRunId && newChatOpen}
      <div class="new-chat-empty" aria-hidden="true"></div>
      <ChatComposer mode="fresh" onSend={sendFresh} onNewChat={createChat} />
    {:else if !selectedRunId}
      <div class="chats-detail-empty"><button class="sidebar-primary" onclick={createChat}>New chat</button></div>
    {:else}
      <div class="chat-detail-toolbar">
        <button class="chat-detail-back" onclick={() => onSelect(null)}>‹ <span>All chats</span></button>
        {#if detail}<span class={"result-pill status-" + (turns.at(-1)?.status || detail.status)}>{turns.length > 1 ? "Latest reply · " + turnStatus(turns.at(-1)?.status || detail.status) : statusLabel(detail.status)}</span>{/if}
      </div>
      <div class="chat-transcript-scroll" bind:this={scrollPane}>
      {#if detailError}<div class="result-error" role="alert">{detailError}</div>{/if}
      {#if loadingDetail && !detail}<p class="chats-empty">Loading run…</p>{/if}
      {#if detail}
        <div class="chat-detail-content">
          {#if turnsError}<p class="result-error" role="alert">{turnsError}</p>{/if}
          {#each turns as turn, index (turn.reply_id || detail.send_id)}
            <div class="message-group user-group">
              <div class="message-role">
                <span>You {#if index === 0}· Job prompt{:else}· Reply {index}{/if}</span>
                <time class="message-timestamp" datetime={new Date((turn.created_at || detail.created_at) * 1000).toISOString()}>{nzTime(turn.created_at || detail.created_at)}</time>
              </div>
              <div class="prompt-bubble">
                <div class:collapsed={turn.user_text.length > 280 && !expandedPrompts[(detail?.send_id ?? "") + ":" + index]} class="prompt-message">{turn.user_text}</div>
                {#if turn.user_text.length > 280}
                  <button class="prompt-expand" type="button" aria-expanded={Boolean(expandedPrompts[(detail?.send_id ?? "") + ":" + index])} onclick={(event) => void togglePrompt((detail?.send_id ?? "") + ":" + index, event)}>
                    {expandedPrompts[(detail?.send_id ?? "") + ":" + index] ? "Show less" : "Show full prompt"}
                    <svg class:rotated={expandedPrompts[(detail?.send_id ?? "") + ":" + index]} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
                  </button>
                {/if}
              </div>
              {#if index === 0 && detail.images?.length}
                <div class="chat-attachments" aria-label="Attached images">
                  {#each detail.images as attachment (attachment.url)}
                    <a href={attachment.url} target="_blank" rel="noopener noreferrer" title={attachment.name}>
                      <img src={attachment.url} alt={attachment.name} loading="lazy" />
                    </a>
                  {/each}
                </div>
              {/if}
            </div>
            <div class="message-group assistant-group">
              <div class="message-role">
                <span>Assistant {#if turn.status === "generating"}<span class="capture-live">· Capturing</span>{/if}</span>
                {#if turn.assistant_text}
                  <button class="copy-message" type="button" aria-label={"Copy assistant reply " + (index + 1)} onclick={() => copyText(formatStoredResponse(turn.assistant_text, index === 0 ? detail?.source ?? "" : ""), turn.reply_id || selectedRunId || "")}>
                    {copyState === (turn.reply_id || detail.send_id) ? "Copied" : copyState === "error:" + (turn.reply_id || detail.send_id) ? "Copy failed" : "Copy"}
                  </button>
                {/if}
              </div>
              {#if turn.tool_calls?.length}<ToolCalls calls={turn.tool_calls} />{/if}
              {#if turn.assistant_text}
                <ResultMarkdown source={turn.assistant_text} captureSource={index === 0 ? detail.source : ""} />
                {#if turn.status !== "completed"}<p class="partial-note">{turn.status === "generating" ? "Partial response · " : ""}{turnStatus(turn.status)}</p>{/if}
              {:else if !turn.tool_calls?.length}
                <p class="no-response">{turnStatus(turn.status)}</p>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      </div>
      {#key selectedRunId}
        <ChatComposer mode="reply" onSend={sendReply} onNewChat={createChat}
          restoreDraft={["prepared", "preflight_failed"].includes(turns.at(-1)?.status ?? "") ? turns.at(-1)?.user_text ?? "" : ""}
          retryablePreflight={turns.at(-1)?.status === "preflight_failed"}
          sendDisabled={Boolean(replyBlockedReason) || recoveringReply}
          sendHint={replyBlockedReason} />
      {/key}
    {/if}
  </div>
</section>
