<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import JobsPage from "./JobsPage.svelte";
  import ChatComposer from "./ChatComposer.svelte";
  import ResultMarkdown from "./ResultMarkdown.svelte";
  import ToolCalls from "./ToolCalls.svelte";
  import { subscribeLiveUpdates } from "./liveUpdates";
  import { recoverVisibleTurns } from "./turnRecovery";
  import { nextResultPageOffset, reconcileResultPage } from "./resultListRefresh";
  import { localGet, localReadTimeoutMs } from "./localRead";
  import { localPost } from "./localMutation";
  import {
    acknowledgeExactReplyRequest,
    acknowledgeQueuedFollowupRequest,
    pendingExactReplyRequest,
    pendingQueuedFollowupRequest,
  } from "./pendingExactReply";
  import { acknowledgeFreshQueueRequest, findFreshQueueReceiptStatus, freshQueueRequest } from "./freshQueueReceipt";
  import {
    chatMessageTime, formatStoredResponse, statusLabel, turnStatus,
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
  const readSyncKey = "prompta.local-read-sync.v1";
  const statuses: { value: ResultStatus | ""; label: string }[] = [
    { value: "", label: "All states" },
    { value: "accepted", label: "Accepted" },
    { value: "generating", label: "Generating" },
    { value: "completed", label: "Completed" },
    { value: "interrupted", label: "Interrupted" },
    { value: "unavailable", label: "Unavailable" },
    { value: "queued", label: "Queued" },
  ];

  function responseBadge(status: LocalTurn["status"]): string {
    switch (status) {
      case "completed": return "Final";
      case "generating": return "Live";
      case "interrupted": return "Interrupted";
      case "unavailable": return "Unavailable";
      case "outcome_unknown": return "Uncertain";
      case "preflight_failed": return "Not sent";
      case "dispatching": return "Sending";
      case "accepted": return "Waiting";
      case "queued": return "Queued";
      case "prepared": return "Draft";
    }
  }

  type WaitingJob = { name: string; position: number; reason: "global" | "stage"; occupied: number; limit: number };
  type QueueSnapshot = { max_workers: number | null; occupied_slots: number; waiting: WaitingJob[] };
  let queueSnapshot = $state<QueueSnapshot>({ max_workers: null, occupied_slots: 0, waiting: [] });
  let queueError = $state("");
  let queueGeneration = 0;
  let queueInFlight = false;
  let queueRefreshPending = false;
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
  let optimisticReads = $state<Record<string, string>>({});
  let readError = $state("");
  let markingAllRead = $state(false);
  let baselineAt = $state(0);
  let drawerOpen = $state(false);
  let drawerProgress = $state<number | null>(null);
  const visibleDrawerProgress = $derived(drawerProgress ?? (drawerOpen ? 1 : 0));
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
  let sidebarPane = $state<HTMLElement>();
  let jobsWorkspace = $state<HTMLDivElement>();
  let searchInput = $state<HTMLInputElement>();
  let loadingList = $state(true);
  let loadingDetail = $state(false);
  let listError = $state("");
  let morePageFailed = $state(false);
  let detailError = $state("");
  let listGeneration = 0;
  let listInFlight = false;
  let listRefreshPending = false;
  let pinsGeneration = 0;
  let detailGeneration = 0;
  let detailInFlightFor: string | null = null;
  let detailRefreshFor: string | null = null;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let liveRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let swipeStart: {
    identifier: number;
    x: number;
    y: number;
    opening: boolean;
    width: number;
    locked: boolean;
    rejected: boolean;
    lastX: number;
    lastTime: number;
    velocityX: number;
  } | null = null;

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
    if (!detail || detail.send_id !== selectedRunId || !latest) return "Loading reply availability…";
    if (latest.status === "prepared" || latest.status === "preflight_failed") {
      return latest.reply_id && latest.conversation_id && latest.parent_id
        ? "" : "The saved reply target is incomplete. Try again after refreshing.";
    }
    // Terminal capture failures do not mean the conversation itself failed.
    // An explicit Send can recover its parent, or start a contextual fresh chat.
    if (["completed", "interrupted", "unavailable", "outcome_unknown", "queued", "accepted", "generating", "dispatching"].includes(latest.status)) return "";
    return "This reply is not yet ready to resend.";
  });
  let visibleWaiting = $derived(
    statusFilter && statusFilter !== "queued" ? [] :
      queueSnapshot.waiting.filter((job) =>
        !search.trim() || job.name.toLowerCase().includes(search.trim().toLowerCase())
      )
  );
  let unpinned = $derived(items.filter((item) => !pinnedIds.includes(item.send_id)).sort(newestFirst));
  const switchingChat = $derived(view === "chats" && !!selectedRunId && detail?.send_id !== selectedRunId);
  const selectedChatTitle = $derived.by(() => {
    if (detail?.send_id === selectedRunId) return detail.title || detail.job_name || "Chats";
    const summary = [...items, ...pinnedItems].find((item) => item.send_id === selectedRunId);
    return summary?.title || "Chats";
  });

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
    const seenRevision = optimisticReads[item.send_id] || item.last_read_revision ||
      readRevisions[item.send_id];
    if (seenRevision) return seenRevision !== item.last_reply_revision;
    // Keep timestamp-only legacy preferences through the transition.
    return item.last_reply_at > (readAt[item.send_id] ?? baselineAt);
  }

  async function importLegacyReads() {
    const reads = Object.fromEntries(Object.entries(readRevisions).filter(
      ([id, revision]) => id.length > 0 && id.length <= 200 &&
        /^[a-f0-9]{64}$/.test(revision)
    ).slice(0, 2000));
    if (!Object.keys(reads).length) return false;
    try {
      const response = await localPost("./api/local-chat-reads/import", { reads }, { timeoutMs: localReadTimeoutMs });
      if (!response.ok) throw new Error("Read import failed");
      readRevisions = {};
      readError = "";
      savePreferences();
      return true;
    } catch {
      readError = "Saved read status could not be synced yet.";
      return false;
    }
  }

  async function retryReadSync() {
    readError = "";
    const hadLegacy = Object.keys(readRevisions).length > 0;
    if (hadLegacy && !await importLegacyReads()) return;
    if (detail?.send_id === selectedRunId) await markRead(detail);
    await Promise.all([loadList(), loadPins()]);
  }

  async function markRead(item: RunSummary) {
    const revision = item.last_reply_revision;
    if (!revision || item.last_read_revision === revision ||
      optimisticReads[item.send_id] === revision) return;
    optimisticReads = { ...optimisticReads, [item.send_id]: revision };
    try {
      const response = await localPost("./api/local-chat-reads", { send_id: item.send_id, revision }, { timeoutMs: localReadTimeoutMs });
      if (!response.ok) throw new Error("Read receipt rejected");
      readError = "";
      // Notify other tabs only after SQLite has confirmed this read.
      try {
        localStorage.setItem(readSyncKey, item.send_id + ":" + Date.now());
      } catch {
        // A blocked storage event does not undo a confirmed server receipt.
      }
    } catch {
      if (optimisticReads[item.send_id] === revision) {
        const next = { ...optimisticReads };
        delete next[item.send_id];
        optimisticReads = next;
      }
      readError = "Could not save read status. Try opening the chat again.";
      void loadList();
    }
  }

  async function markAllRead() {
    if (markingAllRead) return;
    markingAllRead = true;
    readError = "";
    try {
      const response = await localPost("./api/local-chat-reads/all", {}, { timeoutMs: localReadTimeoutMs });
      if (!response.ok) throw new Error("Bulk read receipt rejected");
      // Keep already-loaded off-page entries in place while refreshing the first page.
      const asRead = (item: RunSummary): RunSummary => item.last_reply_revision
        ? { ...item, last_read_revision: item.last_reply_revision } : item;
      items = items.map(asRead);
      pinnedItems = pinnedItems.map(asRead);
      optimisticReads = {};
      await Promise.all([loadList(), loadPins()]);
      try {
        localStorage.setItem(readSyncKey, "all:" + Date.now());
      } catch {
        // The server receipt remains durable if cross-tab notification is unavailable.
      }
    } catch {
      readError = "Could not mark all chats as read. Try again.";
    } finally {
      markingAllRead = false;
    }
  }

  function onReadStorage(event: StorageEvent) {
    if (event.key !== readSyncKey) return;
    void loadList();
    void loadPins();
    if (view === "chats" && selectedRunId) void loadDetail(selectedRunId);
  }

  async function loadPins() {
    const generation = ++pinsGeneration;
    if (pendingPinWrites) return;
    try {
      if (legacyPinIds.length) {
        const imported = await localPost("./api/local-chat-pins/import", { send_ids: legacyPinIds }, { timeoutMs: localReadTimeoutMs });
        if (!imported.ok) throw new Error("Local pin import failed");
        legacyPinIds = [];
        savePreferences();
      }
      const response = await localGet("./api/local-chat-pins");
      if (!response.ok) throw new Error("Local pins unavailable");
      const body: { items: RunSummary[] } = await response.json();
      if (generation !== pinsGeneration || pendingPinWrites) return;
      confirmedPins = body.items;
      pinnedItems = body.items;
      pinnedIds = body.items.map((item) => item.send_id);
      pinsReady = true;
      pinError = "";
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
        const response = await localPost("./api/local-chat-pins", { send_id: item.send_id, pinned: next }, { timeoutMs: localReadTimeoutMs });
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
    if (queueInFlight) {
      queueRefreshPending = true;
      return;
    }
    queueInFlight = true;
    const generation = ++queueGeneration;
    try {
      const response = await localGet("./api/queue-status");
      if (!response.ok) throw new Error("Queue status unavailable");
      const body: QueueSnapshot = await response.json();
      if (generation === queueGeneration) {
        queueSnapshot = body;
        queueError = "";
      }
    } catch {
      // Keep the last confirmed snapshot, but never present it as live status.
      if (generation === queueGeneration) queueError = "Waiting-job status may be out of date.";
    } finally {
      queueInFlight = false;
      if (queueRefreshPending) {
        queueRefreshPending = false;
        void loadQueue();
      }
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
    if (!reset && listInFlight) {
      // EventSource and periodic repairs must not repeatedly supersede a slow
      // GET, leaving the list in a permanent loading or stale-error state.
      listRefreshPending = true;
      return;
    }
    const generation = ++listGeneration;
    listInFlight = true;
    loadingMore = false; // A fresh first-page response supersedes an in-flight append.
    if (reset) {
      items = [];
      total = 0;
      nextOffset = 0;
      if (listPane) listPane.scrollTop = 0;
    }
    loadingList = items.length === 0;
    try {
      const response = await localGet("./api/results?" + resultsParams(0));
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      items = reset ? body.items : reconcileResultPage(items, body.items, body.total, pageSize, statusFilter);
      total = body.total;
      nextOffset = Math.min(body.total, Math.max(nextOffset, body.items.length));
      listError = "";
      morePageFailed = false;
    } catch {
      if (generation === listGeneration) {
        morePageFailed = false;
        listError = "Local results are temporarily unavailable.";
      }
    } finally {
      if (generation === listGeneration) {
        loadingList = false;
        await tick();
        maybeLoadMore();
        listInFlight = false;
        if (listRefreshPending) {
          listRefreshPending = false;
          void loadList();
        }
      }
    }
  }

  async function loadMore() {
    if (loadingMore || loadingList || nextOffset >= total) return;
    const generation = listGeneration;
    const offset = nextOffset;
    loadingMore = true;
    try {
      const response = await localGet("./api/results?" + resultsParams(offset));
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      const next = nextResultPageOffset(offset, body.items.length, body.total);
      if (next === null) {
        // Avoid a request storm when concurrent deletions invalidate the offset.
        // An explicit Retry can revisit this page after the list settles.
        morePageFailed = true;
        listError = "Older chats changed while loading. Retry this page to resync.";
        return;
      }
      items = mergeRuns(items, body.items);
      total = body.total;
      nextOffset = next;
      morePageFailed = false;
      listError = "";
    } catch {
      if (generation === listGeneration) {
        morePageFailed = true;
        listError = "More local chats could not be loaded.";
      }
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
    if (selectedRunId !== id || view !== "chats") return;
    if (detailInFlightFor === id) {
      // Coalesce five-second polling and stream invalidations. Otherwise each
      // request could supersede the previous one during a slow local outage.
      detailRefreshFor = id;
      return;
    }
    detailInFlightFor = id;
    const generation = ++detailGeneration;
    const newSelection = detail?.send_id !== id;
    if (newSelection) {
      // Keep the previous transcript mounted behind the loading cover until
      // the next chat is ready; clearing it causes a visible empty/full jump.
      detailError = "";
      turnsError = "";
    }
    const followTail = newSelection || !!scrollPane &&
      scrollPane.scrollHeight - scrollPane.scrollTop - scrollPane.clientHeight < 96;
    loadingDetail = true;
    try {
      const path = "./api/results/" + encodeURIComponent(id);
      // Both reads start together, but the optional turns endpoint cannot
      // hold the primary transcript behind the chat-switch loading cover.
      const replyRequest = localGet(path + "/turns").then(async (replyResponse): Promise<LocalTurn[] | null> => {
        if (!replyResponse.ok) return null;
        const saved = await replyResponse.json() as { turns?: LocalTurn[] };
        return Array.isArray(saved.turns) ? saved.turns : null;
      }).catch((): null => null);
      const response = await localGet(path);
      if (!response.ok) throw new Error("Result not found");
      const body: RunDetail = await response.json();
      if (generation !== detailGeneration || selectedRunId !== id) return;
      detail = body;
      const originalTurn: LocalTurn = {
        reply_id: "", user_text: body.user_text, assistant_text: body.assistant_text,
        tool_calls: body.tool_calls,
        status: body.status, created_at: body.created_at, updated_at: body.updated_at,
      };
      turns = recoverVisibleTurns(null, turns, originalTurn, !newSelection);
      turnsError = "";
      detailError = "";
      loadingDetail = false;
      if (view === "chats" && selectedRunId === id) markRead(body);
      await tick();
      if (followTail && scrollPane && selectedRunId === id) scrollPane.scrollTop = scrollPane.scrollHeight;
      const savedTurns = await replyRequest;
      if (generation !== detailGeneration || selectedRunId !== id) return;
      turns = recoverVisibleTurns(savedTurns, turns, originalTurn, true);
      turnsError = !savedTurns
        ? "Saved replies are temporarily unavailable; showing the last confirmed turns."
        : "";
      if (followTail) {
        await tick();
        if (scrollPane && selectedRunId === id) scrollPane.scrollTop = scrollPane.scrollHeight;
      }
    } catch {
      if (generation === detailGeneration) detailError = "This run is unavailable locally.";
    } finally {
      if (generation === detailGeneration) loadingDetail = false;
      if (detailInFlightFor === id) {
        detailInFlightFor = null;
        if (detailRefreshFor === id) {
          detailRefreshFor = null;
          if (selectedRunId === id && view === "chats") void loadDetail(id);
        }
      }
    }
  }

  function receiptFailureMessage(error: unknown, fallback: string): string {
    const message = error instanceof Error ? error.message : "";
    return message.startsWith("Unresolved chat receipts") ||
      message.startsWith("Unresolved chat requests") ||
      message.startsWith("Unresolved reply receipts")
      ? message : fallback;
  }

  async function sendFresh(text: string, images: string[]) {
    let request: Awaited<ReturnType<typeof freshQueueRequest>>;
    try {
      request = await freshQueueRequest(text, images);
    } catch (error) {
      return { ok: false, message: receiptFailureMessage(error, "A durable request ID could not be created. Nothing was sent.") };
    }
    const accepted = (sendId: string, status: string) => {
      // A durable record is not necessarily a successful send. Never clear an
      // uncertain request ID or present a dead-letter receipt as accepted.
      if (status === "outcome_unknown") {
        void loadList();
        return { ok: false, message: "The previous fresh-chat send may have reached ChatGPT. No automatic resend was attempted; inspect its status in Chats." };
      }
      if (status === "cancelled" || status === "dead_lettered") {
        void loadList();
        return { ok: false, message: "The earlier request ended without a confirmed delivery. Review its status in Chats before starting another." };
      }
      if (!["queued", "running", "retrying", "rate_limited", "succeeded"].includes(status)) {
        return { ok: false, message: "The queue receipt has an unknown state; the saved request ID was preserved." };
      }
      acknowledgeFreshQueueRequest(request.fingerprint, request.requestId);
      // A confirmed queue receipt is enough to navigate; never send again.
      search = "";
      statusFilter = "";
      onQueued(sendId);
      void loadList();
      void loadPins();
      return { ok: true, message: "" };
    };
    // A previous POST may have persisted despite a lost response or page reload.
    // Reconcile the exact local request first; a GET cannot dispatch another chat.
    if (request.reused) {
      const existing = await findFreshQueueReceiptStatus(request.requestId);
      if (existing) return accepted(existing.sendId, existing.status);
    }
    try {
      const response = await localPost("./api/chats", { request_id: request.requestId, prompt: text, images });
      if (response.ok) {
        const body = await response.json() as { send_id?: string; status?: string };
        if (body.send_id === "manual-" + request.requestId && typeof body.status === "string") {
          return accepted(body.send_id, body.status);
        }
      } else if (response.status < 500) {
        return { ok: false, message: "The fresh chat was rejected. Review the prompt or images." };
      }
    } catch {
      // The request may already exist. Check local SQLite before reporting loss.
    }
    const recovered = await findFreshQueueReceiptStatus(request.requestId);
    if (recovered) return accepted(recovered.sendId, recovered.status);
    return {
      ok: false, ambiguous: true,
      message: "Queue receipt is uncertain. The request ID is saved; press Send again to reconcile it safely.",
    };
  }

  async function recoverReply(sendId: string): Promise<string> {
    if (recoveringReply) return "";
    recoveringReply = true;
    try {
      // A Send click is the explicit user action that permits exact-branch
      // verification. Opening or refreshing a chat never contacts ChatGPT.
      const response = await localPost("./api/results/" + encodeURIComponent(sendId) + "/reply-recover", {}, { timeoutMs: 90_000 });
      if (!response.ok) return "";
      const recovered = await response.json() as { message_id?: string };
      return selectedRunId === sendId ? recovered.message_id ?? "" : "";
    } catch {
      return "";
    } finally {
      recoveringReply = false;
    }
  }

  function freshContinuationPrompt(text: string): string {
    const introduction = "Continue the following saved conversation in a new chat. The previous ChatGPT branch could not be verified. Treat the quoted transcript as context, then answer the final new message.\n\n";
    const finalMessage = "\n\nNew user message:\n" + text;
    if (introduction.length + finalMessage.length >= 32000) return text;
    const transcript = turns.map((turn) =>
      "User:\n" + turn.user_text + (turn.assistant_text ? "\n\nAssistant:\n" + turn.assistant_text : "")
    ).join("\n\n");
    return introduction + transcript.slice(-Math.max(0, 32000 - introduction.length - finalMessage.length)) + finalMessage;
  }

  function originalImageRefs(): string[] {
    return (detail?.images ?? [])
      .filter((attachment) => attachment.url.startsWith("./api/images/"))
      .map((attachment) => attachment.url.slice("./api/images/".length));
  }

  async function queueEarlyReply(sendId: string, text: string) {
    let request: Awaited<ReturnType<typeof pendingQueuedFollowupRequest>>;
    try {
      request = await pendingQueuedFollowupRequest(sendId, text);
    } catch (error) {
      return { ok: false, message: receiptFailureMessage(error, "A durable follow-up ID could not be created. Nothing was sent.") };
    }
    try {
      const response = await localPost(
        "./api/results/" + encodeURIComponent(sendId) + "/reply-queue",
        { reply_id: request.replyId, text },
      );
      if (!response.ok) {
        const problem = response.status < 500
          ? await response.json().catch(() => null) as { error?: string } | null : null;
        return {
          ok: false, ambiguous: response.status >= 500,
          message: problem?.error || "Follow-up queue receipt is uncertain. Retry with the saved draft to reconcile.",
        };
      }
      const receipt = await response.json() as { turn?: { reply_id?: string } };
      if (receipt.turn?.reply_id !== request.replyId) {
        return { ok: false, ambiguous: true, message: "Follow-up receipt did not match. The saved ID will be reused on retry." };
      }
      acknowledgeQueuedFollowupRequest(sendId, request.fingerprint, request.replyId);
      if (selectedRunId === sendId) await loadDetail(sendId);
      return { ok: true, message: "" };
    } catch {
      return { ok: false, ambiguous: true, message: "Queue receipt was lost. The draft is saved; press Send to reconcile." };
    }
  }

  async function sendReply(text: string, _images: string[]) {
    const sendId = selectedRunId;
    if (!sendId || detail?.send_id !== sendId) {
      return { ok: false, message: "The selected chat is still loading. Nothing was sent." };
    }
    const latest = turns.at(-1);
    if (latest && ["queued", "accepted", "generating", "dispatching"].includes(latest.status)) {
      return queueEarlyReply(sendId, text);
    }
    if (latest?.status === "prepared" || latest?.status === "preflight_failed") {
      if (latest.queued_by_user && text !== latest.user_text) return queueEarlyReply(sendId, text);
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
    if (!latest || !["completed", "interrupted", "unavailable", "outcome_unknown"].includes(latest.status)) {
      return { ok: false, message: "Wait for the current response to finish." };
    }
    if (!latest.conversation_id) {
      return sendFresh(freshContinuationPrompt(text), originalImageRefs());
    }
    // Explicit Send is the sole trigger for recovering a persisted ChatGPT branch.
    // Failed or partial response capture must never permanently lock the composer.
    const parentId = latest.message_id || await recoverReply(sendId);
    if (!parentId) {
      if (selectedRunId !== sendId) {
        return { ok: false, message: "The selected chat changed. Nothing was sent." };
      }
      return {
        ok: false,
        message: "The exact ChatGPT branch could not be verified yet. Press Send to retry, or continue in a new chat.",
        fallbackAvailable: true,
      };
    }
    if (selectedRunId !== sendId) {
      return { ok: false, message: "The selected chat changed. Nothing was sent." };
    }
    // Persist the immutable parent/text fingerprint before any possible dispatch.
    // A lost response followed by a reload must reuse the same server receipt ID.
    let request: Awaited<ReturnType<typeof pendingExactReplyRequest>>;
    try {
      request = await pendingExactReplyRequest(sendId, latest.conversation_id, parentId, text);
    } catch (error) {
      return { ok: false, message: receiptFailureMessage(error, "A durable reply ID could not be created. Nothing was sent.") };
    }
    if (selectedRunId !== sendId) {
      return { ok: false, message: "The selected chat changed. Nothing was sent." };
    }
    return sendExactReply(sendId, {
      reply_id: request.replyId,
      conversation_id: latest.conversation_id,
      parent_id: parentId,
      text,
    }, request);
  }

  async function sendExactReply(sendId: string, payload: {
    reply_id: string; conversation_id: string; parent_id: string; text: string;
  }, request?: { replyId: string; fingerprint: string }) {
    try {
      const response = await localPost("./api/results/" + encodeURIComponent(sendId) + "/reply-send", payload);
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
      const receipt = await response.json() as { turn?: { status?: string } };
      if (receipt.turn?.status === "outcome_unknown") {
        if (selectedRunId === sendId) await loadDetail(sendId);
        return { ok: false, message: "The prior send is uncertain. Press Send to attempt branch recovery or continue in a new chat." };
      }
      if (request) acknowledgeExactReplyRequest(request.fingerprint, request.replyId);
      if (selectedRunId === sendId) await loadDetail(sendId);
      return { ok: true, message: "" };
    } catch {
      return {
        ok: false, ambiguous: true,
        message: "Reply acknowledgment was lost. Check local turns; no automatic retry.",
      };
    }
  }

  async function retryFailedTurn(turn: LocalTurn) {
    const sendId = selectedRunId;
    if (!sendId || turn.status !== "preflight_failed" || !turn.reply_id ||
        !turn.conversation_id || !turn.parent_id) return;
    const result = await sendExactReply(sendId, {
      reply_id: turn.reply_id, conversation_id: turn.conversation_id,
      parent_id: turn.parent_id, text: turn.user_text,
    });
    if (selectedRunId === sendId) turnsError = result.ok ? "" : result.message;
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

  const clampDrawer = (value: number) => Math.max(0, Math.min(1, value));

  function cancelSwipe() {
    swipeStart = null;
    drawerProgress = null;
  }

  function startSwipe(event: TouchEvent) {
    if (swipeStart || !window.matchMedia("(max-width: 680px)").matches || event.touches.length !== 1) return;
    const touch = event.touches[0];
    const showList = view === "chats" && !selectedRunId && !newChatOpen;
    if (showList || (!drawerOpen && touch.clientX > 120)) return;
    swipeStart = {
      identifier: touch.identifier,
      x: touch.clientX,
      y: touch.clientY,
      opening: !drawerOpen,
      width: sidebarPane?.getBoundingClientRect().width || Math.min(340, innerWidth - 44),
      locked: false,
      rejected: false,
      lastX: touch.clientX,
      lastTime: performance.now(),
      velocityX: 0,
    };
  }

  function moveSwipe(event: TouchEvent) {
    const gesture = swipeStart;
    if (!gesture || gesture.rejected) return;
    if (event.touches.length !== 1 || event.touches[0].identifier !== gesture.identifier) {
      cancelSwipe();
      return;
    }
    const touch = event.touches[0];
    const dx = touch.clientX - gesture.x;
    const dy = touch.clientY - gesture.y;
    if (!gesture.locked) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 10) return;
      if (Math.abs(dy) >= Math.abs(dx) / 1.15) {
        gesture.rejected = true;
        return;
      }
      if ((gesture.opening && dx <= 0) || (!gesture.opening && dx >= 0)) return;
      gesture.locked = true;
    }
    // Own only horizontal gestures; leave vertical chat scrolling and text inputs alone.
    event.preventDefault();
    const now = performance.now();
    const dt = now - gesture.lastTime;
    if (dt > 0) {
      const instantVelocity = (touch.clientX - gesture.lastX) / dt;
      gesture.velocityX = gesture.velocityX * 0.35 + instantVelocity * 0.65;
    }
    gesture.lastX = touch.clientX;
    gesture.lastTime = now;
    drawerProgress = clampDrawer((gesture.opening ? 0 : 1) + dx / gesture.width);
  }

  function finishSwipe(event: TouchEvent) {
    const gesture = swipeStart;
    if (!gesture) return;
    const touch = Array.from(event.changedTouches).find((item) => item.identifier === gesture.identifier);
    if (!touch) return;
    if (gesture.locked) {
      const dx = touch.clientX - gesture.x;
      const progress = clampDrawer((gesture.opening ? 0 : 1) + dx / gesture.width);
      const fling = Math.abs(dx) >= 30 && Math.abs(gesture.velocityX) >= 0.45 &&
        performance.now() - gesture.lastTime < 120;
      drawerOpen = fling ? gesture.velocityX > 0 : gesture.opening ? progress >= 0.35 : progress > 0.65;
    }
    cancelSwipe();
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
    // The one-time legacy read import is optional. A stalled import must never
    // hold the entire chat rail hostage while local results are available.
    void loadList();
    void loadPins();
    void importLegacyReads().then((imported) => {
      if (imported) void loadList();
    });
    void loadQueue();
    window.addEventListener("storage", onReadStorage);
    window.addEventListener("touchmove", moveSwipe, { passive: false });
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
      window.removeEventListener("storage", onReadStorage);
      window.removeEventListener("touchmove", moveSwipe);
      clearInterval(queuePollTimer);
      clearInterval(detailPollTimer);
      clearTimeout(liveRefreshTimer);
      clearTimeout(searchTimer);
    };
  });
</script>

<svelte:window onkeydown={escapeDrawer} ontouchstart={startSwipe} ontouchend={finishSwipe} ontouchcancel={cancelSwipe} />

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

<section class:drawer-open={drawerOpen} class:drawer-interacting={drawerProgress !== null}
  class:show-list={view === "chats" && !selectedRunId && !newChatOpen} class="chats-layout"
  style:--drawer-offset={`${(visibleDrawerProgress - 1) * 100}%`}
  style:--drawer-opacity={visibleDrawerProgress * 0.6} aria-label="Prompta local chats and jobs">
  <button type="button" class="drawer-backdrop" aria-label="Close chat sidebar" tabindex={drawerOpen ? 0 : -1} onclick={() => drawerOpen = false}></button>
  <aside class="chats-sidebar" aria-label="Local chat sidebar" bind:this={sidebarPane}>
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
    <div class="sidebar-read-actions">
      <button type="button" class="mark-all-read" onclick={markAllRead} disabled={markingAllRead}
        aria-label="Mark all local chats as read" title="Mark all local chats as read">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m2 12 4 4L16 6M9 12l4 4L23 6" /></svg>
        {markingAllRead ? "Marking as read…" : "Mark all as read"}
      </button>
    </div>
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
    {#if queueError}
      <div class="result-error recovery-error" role="alert">
        <span>{queueError}</span>
        <button type="button" onclick={() => void loadQueue()}>Retry queue status</button>
      </div>
    {/if}
    {#if listError}
      <div class="result-error recovery-error" role="alert">
        <span>{listError}</span>
        <button type="button" onclick={() => morePageFailed ? void loadMore() : void loadList()}>{morePageFailed ? "Retry older chats" : "Retry chats"}</button>
      </div>
    {/if}
    {#if pinError}
      <div class="result-error recovery-error" role="alert">
        <span>{pinError}</span>
        <button type="button" onclick={() => void loadPins()}>Retry pins</button>
      </div>
    {/if}
    {#if readError && (view !== "chats" || !selectedRunId)}
      <div class="result-error recovery-error" role="alert">
        <span>{readError}</span>
        <button type="button" onclick={() => void retryReadSync()}>Retry read status</button>
      </div>
    {/if}
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
        <p class="chats-empty">{listError ? "Chat list temporarily unavailable" : search || statusFilter ? "No matching chats" : "No chats"}</p>
      {:else}
        {#each unpinned as item (item.send_id)}{@render chatItem(item)}{/each}
      {/if}
    </div>
  </aside>

  <div class="chats-detail">
    <div class="workspace-header">
      {#if view === "chats" && selectedRunId}
        <button class="chat-header-back" type="button" aria-label="Back to chats" title="Back to chats" onclick={() => onSelect(null)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
        </button>
      {:else}
        <button class="sidebar-menu" type="button" aria-label="Open chat sidebar" aria-expanded={drawerOpen} onclick={() => drawerOpen = true}>☰</button>
      {/if}
      <strong>{view === "jobs" ? "Jobs" : selectedChatTitle}</strong>
    </div>
    {#if view === "jobs"}
      <div class="jobs-workspace" bind:this={jobsWorkspace}><JobsPage workspace={jobsWorkspace} /></div>
    {:else if !selectedRunId && newChatOpen}
      <div class="new-chat-empty" aria-hidden="true"></div>
      <ChatComposer mode="fresh" onSend={sendFresh} onNewChat={createChat} />
    {:else if !selectedRunId}
      <div class="chats-detail-empty"><button class="sidebar-primary" onclick={createChat}>New chat</button></div>
    {:else}
      {#if readError}
        <div class="result-error recovery-error" role="alert">
          <span>{readError}</span>
          <button type="button" onclick={() => void retryReadSync()}>Retry read status</button>
        </div>
      {/if}
      <div class="chat-transcript-shell">
      <div class="chat-transcript-scroll" bind:this={scrollPane} class:chat-switch-hidden={switchingChat} inert={switchingChat} aria-busy={switchingChat}>
      {#if detailError}
        <div class="result-error recovery-error" role="alert">
          <span>{detailError}</span>
          <button type="button" onclick={() => selectedRunId && void loadDetail(selectedRunId)}>Retry chat</button>
        </div>
      {/if}

      {#if detail}
        <div class="chat-detail-content">
          {#if turnsError}
            <div class="result-error recovery-error" role="alert">
              <span>{turnsError}</span>
              <button type="button" onclick={() => selectedRunId && void loadDetail(selectedRunId)}>Retry replies</button>
            </div>
          {/if}
          {#each turns as turn, index (turn.reply_id || detail.send_id)}
            <div class="message-group user-group">
              <div class="message-role">
                <span class="sr-only">You {#if index === 0}· Job prompt{:else}· Reply {index}{/if}</span>
                <time class="message-timestamp" datetime={new Date((turn.created_at || detail.created_at) * 1000).toISOString()}>{chatMessageTime(turn.created_at || detail.created_at)}</time>
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
            <div class={"message-group assistant-group response-" + turn.status} aria-label={"Assistant response " + (index + 1)}>
              {#if turn.status !== "completed"}
                <div class="message-role response-header">
                  <span class="response-state" role="status">{responseBadge(turn.status)}</span>
                </div>
              {/if}
              {#if turn.tool_calls?.length}<ToolCalls calls={turn.tool_calls} />{/if}
              {#if turn.assistant_text}
                <ResultMarkdown source={turn.assistant_text} captureSource={index === 0 ? detail.source : ""} />
                {#if turn.status !== "completed"}<p class="partial-note">{turn.status === "generating" ? "Partial response · " : ""}{turnStatus(turn.status)}</p>{/if}
                <div class="response-actions">
                  <button class="copy-message" type="button" aria-label={"Copy assistant reply " + (index + 1)} onclick={() => copyText(formatStoredResponse(turn.assistant_text, index === 0 ? detail?.source ?? "" : ""), turn.reply_id || selectedRunId || "")}>
                    {copyState === (turn.reply_id || detail.send_id) ? "Copied" : copyState === "error:" + (turn.reply_id || detail.send_id) ? "Copy failed" : "Copy"}
                  </button>
                </div>
              {:else}
                <p class="no-response">{index > 0 && turn.status === "queued" ? "Follow-up queued · waiting for the preceding response" : turnStatus(turn.status)}</p>
                {#if turn.status === "preflight_failed" && turn.reply_id && turn.conversation_id && turn.parent_id}
                  <button class="row-action" type="button" onclick={() => void retryFailedTurn(turn)}>Retry this follow-up</button>
                {/if}
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      </div>
      {#if switchingChat}
        <div class="chat-switch-cover" role="status" aria-label={detailError ? "Chat unavailable" : "Loading selected chat"}>
          {#if detailError}
            <div class="result-error recovery-error">
              <span>{detailError}</span>
              <button type="button" onclick={() => selectedRunId && void loadDetail(selectedRunId)}>Retry chat</button>
            </div>
          {:else}
            <div class="chat-switch-skeleton" aria-hidden="true">
              <div class="chat-switch-line short"></div>
              <div class="chat-switch-line prompt"></div>
              <div class="chat-switch-line medium"></div>
              <div class="chat-switch-line answer"></div>
              <div class="chat-switch-line answer last"></div>
            </div>
            <span class="sr-only">Loading selected chat…</span>
          {/if}
        </div>
      {/if}
      </div>
      <ChatComposer mode="reply" chatId={selectedRunId} onSend={sendReply}
        onFallbackSend={(text) => sendFresh(freshContinuationPrompt(text), originalImageRefs())}
        onNewChat={createChat}
        restoreDraft={detail?.send_id === selectedRunId && turns.at(-1)?.status === "preflight_failed" ? turns.at(-1)?.user_text ?? "" : ""}
        retryablePreflight={detail?.send_id === selectedRunId && turns.at(-1)?.status === "preflight_failed"}
        sendDisabled={detail?.send_id !== selectedRunId || Boolean(replyBlockedReason) || recoveringReply}
        sendHint={recoveringReply ? "Verifying the exact saved ChatGPT branch…" : replyBlockedReason} />
    {/if}
  </div>
</section>
