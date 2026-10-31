import type React from "react";
import { signal, computed, effect, batch } from "@preact/signals-react";
import { untracked as untrack } from "@preact/signals-core";
import { subscribeLiveUpdates } from "./liveUpdates";
import { emptyQueueSnapshot, isQueueSnapshot, type QueueSnapshot } from "./queueStatus";
import { recoverVisibleTurns } from "./turnRecovery";
import { nextResultPageOffset, reconcileResultPage } from "./resultListRefresh";
import { localGet, localReadTimeoutMs } from "./localRead";
import { localPost, localRejectionDetail } from "./localMutation";
import { pinReceiptConfirmed, readReceiptConfirmed } from "./localReceiptReconciliation";
import {
  acknowledgeExactReplyRequest,
  acknowledgeQueuedFollowupRequest,
  pendingExactReplyRequest,
  pendingQueuedFollowupRequest,
} from "./pendingExactReply";
import {
  acknowledgeFreshQueueRequest,
  findFreshQueueReceiptStatus,
  freshQueueRequest,
} from "./freshQueueReceipt";
import {
  exactReplyReceiptState,
  findExactReplyReceiptState,
  findQueuedFollowupReceiptState,
  queuedFollowupReceiptState,
  type ExactReplyPayload,
} from "./exactReplyReceipt";
import {
  type LocalTurn,
  type ChatListStatus,
  type RunDetail,
  type RunSummary,
} from "./resultFormatting";
export type Props = {
  view: "jobs" | "chats";
  selectedRunId: string | null;
  newChatOpen: boolean;
  onSelect: (sendId: string | null) => void;
  onNavigate: (view: "jobs" | "chats") => void;
  onNewChat: () => void;
  onQueued: (sendId: string) => void;
};
export function createChatsPageController(initialProps: Props) {
  const tick = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

  const view = signal(initialProps.view);
  const selectedRunId = signal(initialProps.selectedRunId);
  const newChatOpen = signal(initialProps.newChatOpen);
  const onSelect = signal(initialProps.onSelect);
  const onNavigate = signal(initialProps.onNavigate);
  const onNewChat = signal(initialProps.onNewChat);
  const onQueued = signal(initialProps.onQueued);

  const pageSize = 20;
  const preferencesKey = "prompta.local-sidebar.v1";
  const readSyncKey = "prompta.local-read-sync.v1";
  const statuses: { value: ChatListStatus; label: string }[] = [
    { value: "", label: "All states" },
    { value: "needs_attention", label: "Needs attention" },
    { value: "accepted", label: "Accepted" },
    { value: "generating", label: "Generating" },
    { value: "completed", label: "Completed" },
    { value: "interrupted", label: "Interrupted" },
    { value: "unavailable", label: "Unavailable" },
    { value: "queued", label: "Queued" },
  ];

  let queueSnapshot = signal<QueueSnapshot>(emptyQueueSnapshot);
  let queueError = signal("");
  let queueGeneration = 0;
  let queueInFlight = false;
  let queueRefreshPending = false;
  let queuePollTimer: ReturnType<typeof setInterval> | undefined;
  let detailPollTimer: ReturnType<typeof setInterval> | undefined;
  let recoveryHealthTimer: ReturnType<typeof setInterval> | undefined;
  let recoveryHealthInFlight = false;
  let lastRecoveryHealthAt = 0;
  const recoveryPauseSeconds = signal(0);
  const recoveryPauseReason = signal("");
  const attentionChats = signal<number | null>(null);
  const recoveryBacklog = signal<number | null>(null);
  const recoveryUnverified = signal<number | null>(null);
  const recoveryReplyBacklog = signal<number | null>(null);
  let items = signal<RunSummary[]>([]);
  let pinnedItems = signal<RunSummary[]>([]);
  let pinnedIds = signal<string[]>([]);
  let legacyPinIds: string[] = [];
  let confirmedPins: RunSummary[] = [];
  let pinsReady = signal(false);
  let pendingPinWrites = 0;
  let pinWriteQueue: Promise<void> = Promise.resolve();
  let pinError = signal("");
  let pinWriteError = false;
  let readAt = signal<Record<string, number>>({});
  let readRevisions = signal<Record<string, string>>({});
  let optimisticReads = signal<Record<string, string>>({});
  let readError = signal("");
  let markingAllRead = signal(false);
  let baselineAt = signal(0);
  let drawerOpen = signal(false);
  let drawerProgress = signal<number | null>(null);
  const visibleDrawerProgress = computed(() => drawerProgress.value ?? (drawerOpen.value ? 1 : 0));
  let filtersOpen = signal(false);
  let expandedPrompts = signal<Record<string, boolean>>({});
  let total = signal(0);
  let nextOffset = signal(0);
  let loadingMore = signal(false);
  let search = signal("");
  let statusFilter = signal<ChatListStatus>("");
  let detail = signal<RunDetail | null>(null);
  let turns = signal<LocalTurn[]>([]);
  let turnsError = signal("");
  let recoveringReply = signal(false);
  const startingNewChatFromFailure = signal(false);
  let copyState = signal("");
  let scrollPane = signal<HTMLDivElement>();
  let listPane = signal<HTMLDivElement>();
  let sidebarPane = signal<HTMLElement>();
  let jobsWorkspace = signal<HTMLDivElement>();
  let searchInput = signal<HTMLInputElement>();
  let loadingList = signal(true);
  let loadingDetail = signal(false);
  let pendingRevealFor = signal<string | null>(null);
  let listError = signal("");
  let morePageFailed = signal(false);
  let detailError = signal("");
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
  let pinned = computed(() => {
    const byId = new Map(
      [...pinnedItems.value, ...items.value].map((item) => [item.send_id, item]),
    );
    const filtered = search.value.trim() || statusFilter.value;
    return pinnedIds.value
      .map((id) => byId.get(id))
      .filter((item): item is RunSummary => !!item)
      .filter((item) => !filtered || items.value.some((listed) => listed.send_id === item.send_id));
  });
  const replyBlockedReason = computed((): string => {
    const latest = turns.value.at(-1);
    if (!detail.value || detail.value.send_id !== selectedRunId.value || !latest)
      return "Loading reply availability…";
    if (latest.status === "prepared" || latest.status === "preflight_failed") {
      return latest.reply_id && latest.conversation_id && latest.parent_id
        ? ""
        : "The saved reply target is incomplete. Try again after refreshing.";
    }
    // Terminal capture failures do not mean the conversation itself failed.
    // An explicit Send can recover its parent, or start a contextual fresh chat.
    if (
      [
        "completed",
        "interrupted",
        "unavailable",
        "outcome_unknown",
        "queued",
        "accepted",
        "generating",
        "dispatching",
      ].includes(latest.status)
    )
      return "";
    return "This reply is not yet ready to resend.";
  });
  let visibleWaiting = computed(() =>
    statusFilter.value && statusFilter.value !== "queued"
      ? []
      : queueSnapshot.value.waiting.filter(
          (job) =>
            !search.value.trim() ||
            job.name.toLowerCase().includes(search.value.trim().toLowerCase()),
        ),
  );
  let unpinned = computed(() =>
    items.value.filter((item) => !pinnedIds.value.includes(item.send_id)).sort(newestFirst),
  );
  const switchingChat = computed(
    () =>
      view.value === "chats" &&
      !!selectedRunId.value &&
      (detail.value?.send_id !== selectedRunId.value ||
        pendingRevealFor.value === selectedRunId.value),
  );
  const selectedChatTitle = computed(() => {
    if (detail.value?.send_id === selectedRunId.value)
      return detail.value.title || detail.value.job_name || "Chats";
    const summary = [...items.value, ...pinnedItems.value].find(
      (item) => item.send_id === selectedRunId.value,
    );
    return summary?.title || "Chats";
  });

  function loadPreferences() {
    try {
      const saved = localStorage.getItem(preferencesKey);
      if (saved) {
        const prefs: {
          baselineAt?: number;
          pinnedIds?: string[];
          readAt?: Record<string, number>;
          readRevisions?: Record<string, string>;
        } = JSON.parse(saved);
        baselineAt.value = Number.isFinite(prefs.baselineAt)
          ? Number(prefs.baselineAt)
          : Date.now() / 1000;
        legacyPinIds = Array.isArray(prefs.pinnedIds)
          ? prefs.pinnedIds.filter((id) => typeof id === "string").slice(0, 24)
          : [];
        readAt.value = prefs.readAt && typeof prefs.readAt === "object" ? prefs.readAt : {};
        readRevisions.value =
          prefs.readRevisions && typeof prefs.readRevisions === "object" ? prefs.readRevisions : {};
      } else baselineAt.value = Date.now() / 1000;
    } catch {
      baselineAt.value = Date.now() / 1000;
    }
    savePreferences();
  }

  function savePreferences() {
    try {
      // Only opaque local send IDs and timestamps are stored, never chat content.
      const recent = Object.entries(readAt.value)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 2000);
      const recentIds = new Set(recent.map(([id]) => id));
      localStorage.setItem(
        preferencesKey,
        JSON.stringify({
          baselineAt: baselineAt.value,
          readAt: Object.fromEntries(recent),
          ...(legacyPinIds.length ? { pinnedIds: legacyPinIds } : {}),
          readRevisions: Object.fromEntries(
            Object.entries(readRevisions.value).filter(([id]) => recentIds.has(id)),
          ),
        }),
      );
    } catch {
      // Private browsing and disabled storage still allow in-memory navigation.
    }
  }

  function isUnread(item: RunSummary) {
    if (!item.last_reply_revision) return false;
    const seenRevision =
      optimisticReads.value[item.send_id] ||
      item.last_read_revision ||
      readRevisions.value[item.send_id];
    if (seenRevision) return seenRevision !== item.last_reply_revision;
    // Keep timestamp-only legacy preferences through the transition.
    return item.last_reply_at > (readAt.value[item.send_id] ?? baselineAt.value);
  }

  async function importLegacyReads() {
    const reads = Object.fromEntries(
      Object.entries(readRevisions.value)
        .filter(
          ([id, revision]) => id.length > 0 && id.length <= 200 && /^[a-f0-9]{64}$/.test(revision),
        )
        .slice(0, 2000),
    );
    if (!Object.keys(reads).length) return false;
    try {
      const response = await localPost(
        "./api/local-chat-reads/import",
        { reads },
        { timeoutMs: localReadTimeoutMs },
      );
      if (!response.ok) throw new Error("Read import failed");
      readRevisions.value = {};
      readError.value = "";
      savePreferences();
      return true;
    } catch {
      readError.value = "Saved read status could not be synced yet.";
      return false;
    }
  }

  async function retryReadSync() {
    readError.value = "";
    const hadLegacy = Object.keys(readRevisions.value).length > 0;
    if (hadLegacy && !(await importLegacyReads())) return;
    if (detail.value?.send_id === selectedRunId.value) await markRead(detail.value);
    await Promise.all([loadList(), loadPins()]);
  }

  async function markRead(item: RunSummary) {
    const revision = item.last_reply_revision;
    if (
      !revision ||
      item.last_read_revision === revision ||
      optimisticReads.value[item.send_id] === revision
    )
      return;
    optimisticReads.value = { ...optimisticReads.value, [item.send_id]: revision };
    try {
      const response = await localPost(
        "./api/local-chat-reads",
        { send_id: item.send_id, revision },
        { timeoutMs: localReadTimeoutMs },
      );
      if (!response.ok) throw new Error("Read receipt rejected");
      readError.value = "";
      // Notify other tabs only after SQLite has confirmed this read.
      try {
        localStorage.setItem(readSyncKey, item.send_id + ":" + Date.now());
      } catch {
        // A blocked storage event does not undo a confirmed server receipt.
      }
    } catch {
      // The local server may have committed before the acknowledgment was lost.
      // Confirm the exact stored revision without another POST.
      if (await readReceiptConfirmed(item.send_id, revision)) {
        readError.value = "";
        try {
          localStorage.setItem(readSyncKey, item.send_id + ":" + Date.now());
        } catch {
          // The durable read receipt is already confirmed.
        }
        return;
      }
      if (optimisticReads.value[item.send_id] === revision) {
        const next = { ...optimisticReads.value };
        delete next[item.send_id];
        optimisticReads.value = next;
      }
      readError.value = "Read status could not be confirmed. Refresh or retry to sync it.";
      void loadList();
    }
  }

  async function markAllRead() {
    if (markingAllRead.value) return;
    markingAllRead.value = true;
    readError.value = "";
    try {
      const response = await localPost(
        "./api/local-chat-reads/all",
        {},
        { timeoutMs: localReadTimeoutMs },
      );
      if (!response.ok) throw new Error("Bulk read receipt rejected");
      const asRead = (item: RunSummary): RunSummary =>
        item.last_reply_revision ? { ...item, last_read_revision: item.last_reply_revision } : item;
      items.value = items.value.map(asRead);
      pinnedItems.value = pinnedItems.value.map(asRead);
      optimisticReads.value = {};
      await Promise.all([loadList(), loadPins()]);
      try {
        localStorage.setItem(readSyncKey, "all:" + Date.now());
      } catch {
        // The server receipt remains durable if cross-tab notification is unavailable.
      }
    } catch {
      // The bulk POST may have committed before its acknowledgment was lost.
      // Refresh using GETs only and let the user verify saved read badges.
      await Promise.all([loadList(), loadPins()]);
      readError.value =
        "Mark-all read status could not be confirmed. Check unread badges before repeating.";
    } finally {
      markingAllRead.value = false;
    }
  }

  function onReadStorage(event: StorageEvent) {
    if (event.key !== readSyncKey) return;
    void loadList();
    void loadPins();
    if (view.value === "chats" && selectedRunId.value) void loadDetail(selectedRunId.value);
  }

  async function loadPins() {
    const generation = ++pinsGeneration;
    if (pendingPinWrites) return;
    try {
      if (legacyPinIds.length) {
        const imported = await localPost(
          "./api/local-chat-pins/import",
          { send_ids: legacyPinIds },
          { timeoutMs: localReadTimeoutMs },
        );
        if (!imported.ok) throw new Error("Local pin import failed");
        legacyPinIds = [];
        savePreferences();
      }
      const response = await localGet("./api/local-chat-pins");
      if (!response.ok) throw new Error("Local pins unavailable");
      const body: { items: RunSummary[] } = await response.json();
      if (generation !== pinsGeneration || pendingPinWrites) return;
      confirmedPins = body.items;
      pinnedItems.value = body.items;
      pinnedIds.value = body.items.map((item) => item.send_id);
      pinsReady.value = true;
      // A successful read cannot confirm a prior failed pin mutation.
      // Preserve its explicit write error until a subsequent mutation succeeds.
      if (!pinWriteError) pinError.value = "";
    } catch {
      if (generation === pinsGeneration && !pinWriteError) {
        pinError.value = "Pinned chats are temporarily unavailable.";
      }
    }
  }

  function retryPins() {
    pinWriteError = false;
    void loadPins();
  }
  function togglePin(item: RunSummary) {
    if (!pinsReady.value) return;
    const next = !pinnedIds.value.includes(item.send_id);
    pinsGeneration += 1; // Ignore older GETs while an explicit change is pending.
    pinWriteError = false;
    pinError.value = "";
    if (next) {
      pinnedIds.value = [item.send_id, ...pinnedIds.value];
      pinnedItems.value = [
        item,
        ...pinnedItems.value.filter((pinnedItem) => pinnedItem.send_id !== item.send_id),
      ];
    } else {
      pinnedIds.value = pinnedIds.value.filter((id) => id !== item.send_id);
      pinnedItems.value = pinnedItems.value.filter(
        (pinnedItem) => pinnedItem.send_id !== item.send_id,
      );
    }
    pendingPinWrites += 1;
    // Serialize requests so rapid pin/unpin operations reach SQLite in click order.
    pinWriteQueue = pinWriteQueue.then(async () => {
      try {
        const response = await localPost(
          "./api/local-chat-pins",
          { send_id: item.send_id, pinned: next },
          { timeoutMs: localReadTimeoutMs },
        );
        if (!response.ok) throw new Error("Local pin update failed");
        confirmedPins = next
          ? [item, ...confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id)]
          : confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id);
        pinWriteError = false;
        pinError.value = "";
      } catch {
        // A timed-out POST may still have committed. A local GET can settle
        // this one pin/unpin without risking a second write.
        if (await pinReceiptConfirmed(item.send_id, next)) {
          confirmedPins = next
            ? [item, ...confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id)]
            : confirmedPins.filter((confirmed) => confirmed.send_id !== item.send_id);
          pinWriteError = false;
          pinError.value = "";
        } else {
          pinWriteError = true;
          pinError.value = "Pin change could not be confirmed. Refresh or retry pins.";
        }
      } finally {
        pendingPinWrites -= 1;
        if (!pendingPinWrites) {
          // A failed request must not leave a phantom optimistic pin on screen.
          pinnedItems.value = confirmedPins;
          pinnedIds.value = confirmedPins.map((confirmed) => confirmed.send_id);
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
      const body: unknown = await response.json();
      if (!isQueueSnapshot(body)) throw new Error("Invalid queue snapshot");
      if (generation === queueGeneration) {
        queueSnapshot.value = body;
        queueError.value = "";
      }
    } catch {
      if (generation === queueGeneration) {
        queueError.value =
          queueSnapshot.value === emptyQueueSnapshot
            ? "Waiting-job status is temporarily unavailable."
            : "Queue status is temporarily unavailable. Showing the last confirmed positions and ETAs.";
      }
    } finally {
      queueInFlight = false;
      if (queueRefreshPending) {
        queueRefreshPending = false;
        void loadQueue();
      }
    }
  }

  async function loadRecoveryPause() {
    if (recoveryHealthInFlight || Date.now() - lastRecoveryHealthAt < 25_000) return;
    recoveryHealthInFlight = true;
    lastRecoveryHealthAt = Date.now();
    try {
      // Only local operational health: never contact ChatGPT for a status label.
      const response = await localGet("./api/health");
      if (!response.ok) return;
      const body = (await response.json()) as {
        recovery?: {
          account_read_backoff_seconds?: number;
          security_pause_seconds?: number;
          global_pace_seconds?: number;
          attention_chats?: number;
          recoverable?: number;
          missing_verified_identity?: number;
          unresolved_reply_captures?: number;
        };
      };
      const delays = [
        {
          seconds: body.recovery?.account_read_backoff_seconds ?? 0,
          reason: "account read cooldown",
        },
        { seconds: body.recovery?.security_pause_seconds ?? 0, reason: "security cooldown" },
        { seconds: body.recovery?.global_pace_seconds ?? 0, reason: "read-only probe pacing" },
      ];
      if (delays.every(({ seconds }) => Number.isFinite(seconds) && seconds >= 0)) {
        const longest = delays.reduce((selected, current) =>
          current.seconds > selected.seconds ? current : selected,
        );
        recoveryPauseSeconds.value = Math.ceil(longest.seconds);
        recoveryPauseReason.value = longest.reason;
      }
      const attention = body.recovery?.attention_chats;
      const backlog = body.recovery?.recoverable;
      const unverified = body.recovery?.missing_verified_identity;
      const replies = body.recovery?.unresolved_reply_captures;
      if (typeof attention === "number" && Number.isSafeInteger(attention) && attention >= 0)
        attentionChats.value = attention;
      if (typeof backlog === "number" && Number.isSafeInteger(backlog) && backlog >= 0)
        recoveryBacklog.value = backlog;
      if (typeof unverified === "number" && Number.isSafeInteger(unverified) && unverified >= 0)
        recoveryUnverified.value = unverified;
      if (typeof replies === "number" && Number.isSafeInteger(replies) && replies >= 0)
        recoveryReplyBacklog.value = replies;
    } catch {
      // Keep the last confirmed value; this is informational, not a send gate.
    } finally {
      recoveryHealthInFlight = false;
    }
  }

  function resultsParams(offset: number) {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
    if (search.value.trim()) params.set("q", search.value.trim());
    if (statusFilter.value) params.set("status", statusFilter.value);
    return params;
  }

  function mergeRuns(previous: RunSummary[], incoming: RunSummary[]) {
    return [
      ...new Map([...previous, ...incoming].map((item) => [item.send_id, item])).values(),
    ].sort(newestFirst);
  }

  function maybeLoadMore() {
    if (
      loadingList.value ||
      loadingMore.value ||
      Boolean(listError.value) ||
      morePageFailed.value ||
      nextOffset.value >= total.value ||
      !listPane.value
    )
      return;
    if (listPane.value.scrollTop + listPane.value.clientHeight >= listPane.value.scrollHeight - 240)
      void loadMore();
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
    loadingMore.value = false; // A fresh first-page response supersedes an in-flight append.
    // A search/filter fetch can fail or time out. Keep the last confirmed rail
    // and its scroll position until the new result page is actually available.
    loadingList.value = items.value.length === 0;
    try {
      const response = await localGet("./api/results?" + resultsParams(0));
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      items.value = reset
        ? body.items
        : reconcileResultPage(items.value, body.items, body.total, pageSize, statusFilter.value);
      total.value = body.total;
      nextOffset.value = reset
        ? Math.min(body.total, body.items.length)
        : Math.min(body.total, Math.max(nextOffset.value, body.items.length));
      if (reset && listPane.value) listPane.value.scrollTop = 0;
      listError.value = "";
      morePageFailed.value = false;
    } catch {
      if (generation === listGeneration) {
        morePageFailed.value = false;
        listError.value = "Local results are temporarily unavailable.";
      }
    } finally {
      if (generation === listGeneration) {
        loadingList.value = false;
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
    if (loadingMore.value || loadingList.value || nextOffset.value >= total.value) return;
    const generation = listGeneration;
    const offset = nextOffset.value;
    loadingMore.value = true;
    try {
      const response = await localGet("./api/results?" + resultsParams(offset));
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      const next = nextResultPageOffset(offset, body.items.length, body.total);
      if (next === null) {
        // Avoid a request storm when concurrent deletions invalidate the offset.
        // An explicit Retry can revisit this page after the list settles.
        morePageFailed.value = true;
        listError.value = "Older chats changed while loading. Retry this page to resync.";
        return;
      }
      items.value = mergeRuns(items.value, body.items);
      total.value = body.total;
      nextOffset.value = next;
      morePageFailed.value = false;
      listError.value = "";
    } catch {
      if (generation === listGeneration) {
        morePageFailed.value = true;
        listError.value = "More local chats could not be loaded.";
      }
    } finally {
      if (generation === listGeneration) {
        loadingMore.value = false;
        await tick();
        // On a tall viewport, continue until the rail actually overflows.
        if (!listError.value) maybeLoadMore();
      }
    }
  }

  async function loadDetail(id: string) {
    if (selectedRunId.value !== id || view.value !== "chats") return;
    if (detailInFlightFor === id) {
      // Coalesce five-second polling and stream invalidations. Otherwise each
      // request could supersede the previous one during a slow local outage.
      detailRefreshFor = id;
      return;
    }
    detailInFlightFor = id;
    const generation = ++detailGeneration;
    const newSelection = detail.value?.send_id !== id;
    if (newSelection) {
      // Keep the cover until the new transcript has been laid out and scrolled.
      // Revealing the content before the scroll adjustment causes a visible snap.
      pendingRevealFor.value = id;
      detailError.value = "";
      turnsError.value = "";
    }
    const followTail =
      newSelection ||
      (!!scrollPane.value &&
        scrollPane.value.scrollHeight - scrollPane.value.scrollTop - scrollPane.value.clientHeight <
          96);
    loadingDetail.value = true;
    try {
      const path = "./api/results/" + encodeURIComponent(id);
      // Both reads start together, but the optional turns endpoint cannot
      // hold the primary transcript behind the chat-switch loading cover.
      const replyRequest = localGet(path + "/turns")
        .then(async (replyResponse): Promise<LocalTurn[] | null> => {
          if (!replyResponse.ok) return null;
          const saved = (await replyResponse.json()) as { turns?: LocalTurn[] };
          return Array.isArray(saved.turns) ? saved.turns : null;
        })
        .catch((): null => null);
      const response = await localGet(path);
      if (!response.ok) throw new Error("Result not found");
      const body: RunDetail = await response.json();
      if (generation !== detailGeneration || selectedRunId.value !== id) return;
      // A quick turns read should join the primary result before first reveal.
      // Never hold the main transcript behind an unhealthy optional endpoint.
      const earlyTurns = newSelection
        ? await Promise.race([
            replyRequest,
            new Promise<undefined>((resolve) => setTimeout(resolve, 100)),
          ])
        : undefined;
      if (generation !== detailGeneration || selectedRunId.value !== id) return;
      detail.value = body;
      const originalTurn: LocalTurn = {
        reply_id: "",
        user_text: body.user_text,
        assistant_text: body.assistant_text,
        tool_calls: body.tool_calls,
        status: body.status,
        created_at: body.created_at,
        updated_at: body.updated_at,
      };
      turns.value = recoverVisibleTurns(
        earlyTurns ?? null,
        turns.value,
        originalTurn,
        !newSelection,
      );
      turnsError.value =
        earlyTurns === null
          ? "Saved replies are temporarily unavailable; showing the last confirmed turns."
          : "";
      detailError.value = "";
      loadingDetail.value = false;
      if (view.value === "chats" && selectedRunId.value === id) void markRead(body);
      await tick();
      if (followTail && scrollPane.value && selectedRunId.value === id)
        scrollPane.value.scrollTop = scrollPane.value.scrollHeight;
      // The cover is removed only after the scroll position is committed.
      if (pendingRevealFor.value === id) pendingRevealFor.value = null;
      const savedTurns = earlyTurns === undefined ? await replyRequest : earlyTurns;
      if (generation !== detailGeneration || selectedRunId.value !== id) return;
      if (earlyTurns === undefined) {
        turns.value = recoverVisibleTurns(savedTurns, turns.value, originalTurn, true);
        turnsError.value = !savedTurns
          ? "Saved replies are temporarily unavailable; showing the last confirmed turns."
          : "";
        if (followTail) {
          await tick();
          if (scrollPane.value && selectedRunId.value === id)
            scrollPane.value.scrollTop = scrollPane.value.scrollHeight;
        }
      }
      if (
        turns.value.some((turn) =>
          ["interrupted", "unavailable", "outcome_unknown"].includes(turn.status),
        )
      )
        void loadRecoveryPause();
    } catch {
      if (generation === detailGeneration) detailError.value = "This run is unavailable locally.";
    } finally {
      if (generation === detailGeneration) loadingDetail.value = false;
      if (detailInFlightFor === id) {
        detailInFlightFor = null;
        if (detailRefreshFor === id) {
          detailRefreshFor = null;
          if (selectedRunId.value === id && view.value === "chats") void loadDetail(id);
        }
      }
    }
  }

  function receiptFailureMessage(error: unknown, fallback: string): string {
    const message = error instanceof Error ? error.message : "";
    return message.startsWith("Unresolved chat receipts") ||
      message.startsWith("Unresolved chat requests") ||
      message.startsWith("Unresolved reply receipts")
      ? message
      : fallback;
  }

  async function sendFresh(text: string, images: string[], scope = "chat") {
    let request: Awaited<ReturnType<typeof freshQueueRequest>>;
    try {
      request = await freshQueueRequest(text, images, scope);
    } catch (error) {
      return {
        ok: false,
        message: receiptFailureMessage(
          error,
          "A durable request ID could not be created. Nothing was sent.",
        ),
      };
    }
    const accepted = (sendId: string, status: string) => {
      // A durable record is not necessarily a successful send. Never clear an
      // uncertain request ID or present a dead-letter receipt as accepted.
      if (status === "outcome_unknown") {
        void loadList();
        return {
          ok: false,
          message:
            "The previous fresh-chat send may have reached ChatGPT. No automatic resend was attempted; inspect its status in Chats.",
        };
      }
      if (status === "cancelled" || status === "dead_lettered") {
        void loadList();
        return {
          ok: false,
          message:
            "The earlier request ended without a confirmed delivery. Review its status in Chats before starting another.",
        };
      }
      if (!["queued", "running", "retrying", "rate_limited", "succeeded"].includes(status)) {
        return {
          ok: false,
          message: "The queue receipt has an unknown state; the saved request ID was preserved.",
        };
      }
      acknowledgeFreshQueueRequest(request.fingerprint, request.requestId);
      // A confirmed queue receipt is enough to navigate; never send again.
      search.value = "";
      statusFilter.value = "";
      onQueued.value(sendId);
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
      const response = await localPost("./api/chats", {
        request_id: request.requestId,
        prompt: text,
        images,
      });
      if (response.ok) {
        const body = (await response.json()) as { send_id?: string; status?: string };
        if (body.send_id === "manual-" + request.requestId && typeof body.status === "string") {
          return accepted(body.send_id, body.status);
        }
      } else if (response.status < 500) {
        // Even a conflicting local response may follow a committed queue write.
        // Confirm the immutable request ID before reporting a rejection.
        const existing = await findFreshQueueReceiptStatus(request.requestId);
        if (existing) return accepted(existing.sendId, existing.status);
        return {
          ok: false,
          message: await localRejectionDetail(
            response,
            "The fresh chat was rejected. Review the prompt or images.",
          ),
        };
      }
    } catch {
      // The request may already exist. Check local SQLite before reporting loss.
    }
    const recovered = await findFreshQueueReceiptStatus(request.requestId);
    if (recovered) return accepted(recovered.sendId, recovered.status);
    return {
      ok: false,
      ambiguous: true,
      message:
        "Queue receipt is uncertain. The request ID is saved; press Send again to reconcile it safely.",
    };
  }

  async function recoverReply(sendId: string): Promise<{ messageId: string; issue?: string }> {
    if (recoveringReply.value)
      return { messageId: "", issue: "Exact-branch verification is already running." };
    recoveringReply.value = true;
    try {
      // Only an explicit Send invokes this read-only, exact-branch verification.
      const response = await localPost(
        "./api/results/" + encodeURIComponent(sendId) + "/reply-recover",
        {},
        { timeoutMs: 90_000 },
      );
      if (!response.ok) {
        if (response.status >= 500)
          return {
            messageId: "",
            issue: "Exact-branch verification is temporarily unavailable. Nothing was sent.",
          };
        return {
          messageId: "",
          issue: await localRejectionDetail(response, "The saved branch cannot be verified yet."),
        };
      }
      const recovered = (await response.json()) as { message_id?: string };
      if (selectedRunId.value !== sendId) return { messageId: "" };
      if (typeof recovered.message_id === "string" && recovered.message_id)
        return { messageId: recovered.message_id };
      return { messageId: "", issue: "Verification returned no assistant identity." };
    } catch {
      return {
        messageId: "",
        issue:
          "Exact-branch verification timed out or lost its local connection. Nothing was sent.",
      };
    } finally {
      recoveringReply.value = false;
    }
  }

  function freshContinuationPrompt(text: string): string {
    const lastResultIndex = turns.value.findLastIndex((turn) =>
      Boolean(turn.assistant_text.trim()),
    );
    const lastResult = lastResultIndex >= 0 ? turns.value[lastResultIndex].assistant_text : "";
    const prefix = lastResult ? "Last saved assistant result:\n" : "Previous chat request:\n";
    const suffix = "\n\nNew user message:\n" + text;
    const available = 32000 - prefix.length - suffix.length;
    if (available <= 0) return text;
    const previousContext = lastResult || detail.value?.user_text || "";
    let result = previousContext;
    if (previousContext.length > available)
      result =
        available > 3
          ? previousContext.slice(0, available - 3) + "..."
          : previousContext.slice(0, available);
    const transcript = turns.value
      .slice(0, lastResultIndex + 1)
      .map(
        (turn, index) =>
          "User:\n" +
          turn.user_text +
          (index !== lastResultIndex && turn.assistant_text
            ? "\n\nAssistant:\n" + turn.assistant_text
            : ""),
      )
      .join("\n\n");
    const contextHeader = "\n\nEarlier conversation context:\n";
    const contextBudget = available - result.length - contextHeader.length;
    const context =
      transcript && contextBudget > 0 ? contextHeader + transcript.slice(-contextBudget) : "";
    return prefix + result + context + suffix;
  }

  async function retryFailedInitialInNewChat(): Promise<void> {
    const sendId = selectedRunId.value;
    const original = turns.value[0];
    if (
      startingNewChatFromFailure.value ||
      !sendId ||
      detail.value?.send_id !== sendId ||
      !original ||
      !["interrupted", "unavailable", "outcome_unknown"].includes(original.status) ||
      Boolean(detail.value.conversation_id || original.conversation_id) ||
      Boolean(original.assistant_text.trim()) ||
      !original.user_text.trim()
    )
      return;
    startingNewChatFromFailure.value = true;
    try {
      // Only this explicit button can create a new request for the same text.
      // A stable source-scoped fingerprint still reconciles a lost queue receipt.
      const result = await sendFresh(
        original.user_text,
        originalImageRefs(),
        "explicit-retry:" + sendId,
      );
      if (!result.ok && selectedRunId.value === sendId) turnsError.value = result.message;
    } finally {
      startingNewChatFromFailure.value = false;
    }
  }

  async function startFailedReplyInNewChat(turn: LocalTurn): Promise<void> {
    const sendId = selectedRunId.value;
    if (
      startingNewChatFromFailure.value ||
      !sendId ||
      detail.value?.send_id !== sendId ||
      !["preflight_failed", "interrupted", "unavailable", "outcome_unknown"].includes(turn.status)
    )
      return;
    startingNewChatFromFailure.value = true;
    try {
      const message = ["preflight_failed", "outcome_unknown"].includes(turn.status)
        ? turn.user_text
        : "Please continue from the last saved result.";
      const result = await sendFresh(freshContinuationPrompt(message), originalImageRefs());
      if (!result.ok && selectedRunId.value === sendId) turnsError.value = result.message;
    } finally {
      startingNewChatFromFailure.value = false;
    }
  }

  function originalImageRefs(): string[] {
    return (detail.value?.images ?? [])
      .filter((attachment) => attachment.url.startsWith("./api/images/"))
      .map((attachment) => attachment.url.slice("./api/images/".length));
  }

  async function queueEarlyReply(sendId: string, text: string) {
    let request: Awaited<ReturnType<typeof pendingQueuedFollowupRequest>>;
    try {
      request = await pendingQueuedFollowupRequest(sendId, text);
    } catch (error) {
      return {
        ok: false,
        message: receiptFailureMessage(
          error,
          "A durable follow-up ID could not be created. Nothing was sent.",
        ),
      };
    }
    const accepted = async () => {
      acknowledgeQueuedFollowupRequest(sendId, request.fingerprint, request.replyId);
      if (selectedRunId.value === sendId) void loadDetail(sendId);
      return { ok: true, message: "" };
    };
    const uncertain = () => ({
      ok: false,
      ambiguous: true,
      message:
        "This follow-up's send outcome is uncertain. Its saved ID is preserved; no additional send was attempted.",
    });
    const reconcile = async () => {
      const state = await findQueuedFollowupReceiptState(sendId, request.replyId, text);
      if (state === "accepted") return accepted();
      if (state === "uncertain") return uncertain();
      if (state === "invalid") {
        return {
          ok: false,
          message: "The saved follow-up ID conflicts with its local receipt. Nothing was resent.",
        };
      }
      return null;
    };
    // A lost HTTP response or reload may have left the queue intent in SQLite.
    // A local GET must settle that receipt before another explicit POST.
    if (request.reused) {
      const existing = await reconcile();
      if (existing) return existing;
    }
    try {
      const response = await localPost(
        "./api/results/" + encodeURIComponent(sendId) + "/reply-queue",
        { reply_id: request.replyId, text },
      );
      if (!response.ok) {
        const existing = await reconcile();
        if (existing) return existing;
        return {
          ok: false,
          ambiguous: response.status >= 500,
          message:
            response.status < 500
              ? await localRejectionDetail(
                  response,
                  "The follow-up was rejected. Its saved request ID was preserved.",
                )
              : "Follow-up queue receipt is uncertain. Retry with the saved draft to reconcile.",
        };
      }
      const receipt = (await response.json()) as { turn?: unknown };
      const state = queuedFollowupReceiptState(receipt.turn, sendId, request.replyId, text);
      if (state === "accepted") return accepted();
      if (state === "uncertain") return uncertain();
      return (
        (await reconcile()) ?? {
          ok: false,
          ambiguous: true,
          message: "Follow-up receipt did not match. The saved ID will be reused on retry.",
        }
      );
    } catch {
      return (
        (await reconcile()) ?? {
          ok: false,
          ambiguous: true,
          message: "Queue receipt was lost. The draft is saved; press Send to reconcile.",
        }
      );
    }
  }

  async function sendReply(text: string, _images: string[]) {
    const sendId = selectedRunId.value;
    if (!sendId || detail.value?.send_id !== sendId) {
      return { ok: false, message: "The selected chat is still loading. Nothing was sent." };
    }
    const latest = turns.value.at(-1);
    if (latest && ["queued", "accepted", "generating", "dispatching"].includes(latest.status)) {
      return queueEarlyReply(sendId, text);
    }
    if (latest?.status === "prepared" || latest?.status === "preflight_failed") {
      if (latest.queued_by_user && text !== latest.user_text) return queueEarlyReply(sendId, text);
      if (
        !latest.reply_id ||
        !latest.conversation_id ||
        !latest.parent_id ||
        text !== latest.user_text
      ) {
        return {
          ok: false,
          message: "A pending reply can only be retried with its original text.",
        };
      }
      return sendExactReply(sendId, {
        reply_id: latest.reply_id,
        conversation_id: latest.conversation_id,
        parent_id: latest.parent_id,
        text: latest.user_text,
      });
    }
    if (
      !latest ||
      !["completed", "interrupted", "unavailable", "outcome_unknown"].includes(latest.status)
    ) {
      return { ok: false, message: "Wait for the current response to finish." };
    }
    if (!latest.conversation_id) {
      return sendFresh(freshContinuationPrompt(text), originalImageRefs());
    }
    // Explicit Send is the sole trigger for recovering a persisted ChatGPT branch.
    // Failed or partial response capture must never permanently lock the composer.
    const verification = latest.message_id
      ? { messageId: latest.message_id }
      : await recoverReply(sendId);
    const parentId = verification.messageId;
    if (!parentId) {
      if (selectedRunId.value !== sendId) {
        return { ok: false, message: "The selected chat changed. Nothing was sent." };
      }
      return {
        ok: false,
        message:
          (verification.issue ?? "The exact ChatGPT branch could not be verified yet.") +
          " Press Send to retry later, or continue in a new chat.",
        fallbackAvailable: true,
      };
    }
    if (selectedRunId.value !== sendId) {
      return { ok: false, message: "The selected chat changed. Nothing was sent." };
    }
    // Persist the immutable parent/text fingerprint before any possible dispatch.
    // A lost response followed by a reload must reuse the same server receipt ID.
    let request: Awaited<ReturnType<typeof pendingExactReplyRequest>>;
    try {
      request = await pendingExactReplyRequest(sendId, latest.conversation_id, parentId, text);
    } catch (error) {
      return {
        ok: false,
        message: receiptFailureMessage(
          error,
          "A durable reply ID could not be created. Nothing was sent.",
        ),
      };
    }
    if (selectedRunId.value !== sendId) {
      return { ok: false, message: "The selected chat changed. Nothing was sent." };
    }
    return sendExactReply(
      sendId,
      {
        reply_id: request.replyId,
        conversation_id: latest.conversation_id,
        parent_id: parentId,
        text,
      },
      request,
    );
  }

  async function sendExactReply(
    sendId: string,
    payload: ExactReplyPayload,
    request?: { replyId: string; fingerprint: string; reused?: boolean },
  ) {
    const accepted = async () => {
      if (request) acknowledgeExactReplyRequest(request.fingerprint, request.replyId);
      if (selectedRunId.value === sendId) void loadDetail(sendId);
      return { ok: true, message: "" };
    };
    const uncertain = () => ({
      ok: false,
      ambiguous: true,
      message:
        "Reply outcome could not be confirmed. Its saved ID was preserved; inspect local turns before another attempt.",
    });
    const reconcile = async () => {
      const state = await findExactReplyReceiptState(sendId, payload);
      if (state === "accepted") return accepted();
      if (state === "uncertain") return uncertain();
      if (state === "invalid")
        return {
          ok: false,
          message: "Saved reply identity conflicts with the server. Nothing was resent.",
        };
      return null;
    };
    // A page reload or lost POST receipt must not need another POST when
    // local SQLite already proves the original exact reply was accepted.
    if (request?.reused) {
      const existing = await reconcile();
      if (existing) return existing;
    }
    try {
      const response = await localPost(
        "./api/results/" + encodeURIComponent(sendId) + "/reply-send",
        payload,
      );
      if (!response.ok) {
        // The exact local turn may have committed before a proxy reported a
        // conflict. Read its immutable receipt before treating any 4xx as final.
        const existing = await reconcile();
        if (existing) return existing;
        if (response.status >= 500) return uncertain();
        return {
          ok: false,
          message: await localRejectionDetail(
            response,
            "Reply was not queued. Check the saved branch and try again.",
          ),
        };
      }
      const receipt: unknown = await response.json();
      const turn =
        receipt && typeof receipt === "object" && "turn" in receipt ? receipt.turn : null;
      const state = exactReplyReceiptState(turn, payload, sendId);
      if (state === "accepted") return accepted();
      if (state === "uncertain") return uncertain();
      if (state === "not_sent")
        return {
          ok: false,
          message:
            "The reply was not authorized for dispatch. Press Send again to retry preflight.",
        };
      return (
        (await reconcile()) ?? {
          ok: false,
          ambiguous: true,
          message: "The reply receipt did not match its saved identity. Nothing was resent.",
        }
      );
    } catch {
      return (await reconcile()) ?? uncertain();
    }
  }

  async function retryFailedTurn(turn: LocalTurn) {
    const sendId = selectedRunId.value;
    if (
      !sendId ||
      turn.status !== "preflight_failed" ||
      !turn.reply_id ||
      !turn.conversation_id ||
      !turn.parent_id
    )
      return;
    const result = await sendExactReply(sendId, {
      reply_id: turn.reply_id,
      conversation_id: turn.conversation_id,
      parent_id: turn.parent_id,
      text: turn.user_text,
    });
    if (selectedRunId.value === sendId) turnsError.value = result.ok ? "" : result.message;
  }

  async function copyText(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      copyState.value = key;
    } catch {
      copyState.value = "error:" + key;
    }
  }

  function refresh() {
    if (!queueError.value) void loadQueue();
    void loadList();
    void loadPins();
    if (view.value === "chats" && selectedRunId.value) void loadDetail(selectedRunId.value);
  }

  function applyFilter() {
    void loadList(true);
  }

  function searchChanged() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilter, 300);
  }

  async function toggleSearch() {
    filtersOpen.value = !filtersOpen.value;
    if (filtersOpen.value) {
      await tick();
      searchInput.value?.focus();
    }
  }

  const clampDrawer = (value: number) => Math.max(0, Math.min(1, value));

  function cancelSwipe() {
    swipeStart = null;
    drawerProgress.value = null;
  }

  function startSwipe(event: TouchEvent) {
    if (
      swipeStart ||
      !window.matchMedia("(max-width: 680px)").matches ||
      event.touches.length !== 1
    )
      return;
    const touch = event.touches[0];
    const showList = view.value === "chats" && !selectedRunId.value && !newChatOpen.value;
    if (showList || (!drawerOpen.value && touch.clientX > 120)) return;
    swipeStart = {
      identifier: touch.identifier,
      x: touch.clientX,
      y: touch.clientY,
      opening: !drawerOpen.value,
      width: sidebarPane.value?.getBoundingClientRect().width || Math.min(340, innerWidth - 44),
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
    drawerProgress.value = clampDrawer((gesture.opening ? 0 : 1) + dx / gesture.width);
  }

  function finishSwipe(event: TouchEvent) {
    const gesture = swipeStart;
    if (!gesture) return;
    const touch = Array.from(event.changedTouches).find(
      (item) => item.identifier === gesture.identifier,
    );
    if (!touch) return;
    if (gesture.locked) {
      const dx = touch.clientX - gesture.x;
      const progress = clampDrawer((gesture.opening ? 0 : 1) + dx / gesture.width);
      const fling =
        Math.abs(dx) >= 30 &&
        Math.abs(gesture.velocityX) >= 0.45 &&
        performance.now() - gesture.lastTime < 120;
      if (fling) drawerOpen.value = gesture.velocityX > 0;
      else if (gesture.opening) drawerOpen.value = progress >= 0.35;
      else drawerOpen.value = progress > 0.65;
    }
    cancelSwipe();
  }

  function selectRun(item: RunSummary) {
    void markRead(item);
    drawerOpen.value = false;
    onSelect.value(item.send_id);
  }

  function showJobs() {
    drawerOpen.value = false;
    onNavigate.value("jobs");
  }

  function createChat() {
    drawerOpen.value = false;
    onNewChat.value();
  }

  function escapeDrawer(event: KeyboardEvent) {
    if (event.key === "Escape" && drawerOpen.value) drawerOpen.value = false;
  }

  async function togglePrompt(key: string, event: React.MouseEvent<HTMLButtonElement>) {
    const bubble = (event.currentTarget as HTMLElement).closest(".prompt-bubble");
    const originalTop = bubble?.getBoundingClientRect().top;
    expandedPrompts.value = { ...expandedPrompts.value, [key]: !expandedPrompts.value[key] };
    await tick();
    // Keep the start of the bubble in place instead of letting scroll anchoring grow it upward.
    if (bubble && scrollPane.value && originalTop !== undefined) {
      scrollPane.value.scrollTop += bubble.getBoundingClientRect().top - originalTop;
    }
  }

  const onMountImpl = () => {
    loadPreferences();
    // The one-time legacy read import is optional. A stalled import must never
    // hold the entire chat rail hostage while local results are available.
    void loadList();
    void loadPins();
    void importLegacyReads().then((imported) => {
      if (imported) void loadList();
    });
    void loadQueue();
    void loadRecoveryPause();
    window.addEventListener("storage", onReadStorage);
    window.addEventListener("touchmove", moveSwipe, { passive: false });
    queuePollTimer = setInterval(() => {
      if (document.visibilityState === "visible") void loadQueue();
    }, 15000);
    // Poll only Prompta's local turn record while an explicit reply is active.
    // This never opens ChatGPT or submits another message.
    recoveryHealthTimer = setInterval(() => {
      if (document.visibilityState === "visible") void loadRecoveryPause();
    }, 30_000);
    detailPollTimer = setInterval(() => {
      if (document.visibilityState !== "visible" || view.value !== "chats" || !selectedRunId.value)
        return;
      if (
        ["prepared", "dispatching", "accepted", "generating"].includes(
          turns.value.at(-1)?.status ?? "",
        )
      ) {
        void loadDetail(selectedRunId.value);
      }
    }, 5000);
    const unsubscribeJobs = subscribeLiveUpdates("jobs", () => {
      // Keep a failed read actionable until explicit retry or the next 15s poll.
      if (!queueError.value) void loadQueue();
    });
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
      clearInterval(recoveryHealthTimer);
      clearTimeout(liveRefreshTimer);
      clearTimeout(searchTimer);
    };
  };
  function mount() {
    const cleanup = onMountImpl();
    const disposers = [
      effect(() => {
        const id = view.value === "chats" ? selectedRunId.value : null;
        untrack(() => {
          if (id) void loadDetail(id);
          else {
            detailGeneration += 1;
            detail.value = null;
            turns.value = [];
            turnsError.value = "";
            detailError.value = "";
          }
        });
      }),
    ];
    return () => {
      for (const dispose of disposers) dispose();
      if (typeof cleanup === "function") cleanup();
    };
  }
  function syncProps(next: Props) {
    batch(() => {
      if (view.peek() !== next.view) view.value = next.view;
      if (selectedRunId.peek() !== next.selectedRunId) selectedRunId.value = next.selectedRunId;
      if (newChatOpen.peek() !== next.newChatOpen) newChatOpen.value = next.newChatOpen;
      if (onSelect.peek() !== next.onSelect) onSelect.value = next.onSelect;
      if (onNavigate.peek() !== next.onNavigate) onNavigate.value = next.onNavigate;
      if (onNewChat.peek() !== next.onNewChat) onNewChat.value = next.onNewChat;
      if (onQueued.peek() !== next.onQueued) onQueued.value = next.onQueued;
    });
  }
  return {
    retryPins,
    view,
    selectedRunId,
    newChatOpen,
    onSelect,
    statuses,
    queueSnapshot,
    queueError,
    recoveryPauseSeconds,
    recoveryPauseReason,
    attentionChats,
    recoveryBacklog,
    recoveryUnverified,
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
    scrollPane,
    listPane,
    sidebarPane,
    jobsWorkspace,
    searchInput,
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
    mount,
    syncProps,
  };
}
