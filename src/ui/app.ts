import {
  chatBrokenReferenceAt,
  chatIsBroken,
  chatLastAssistantAt,
  chatListRequestUrl,
  clientIdBelongsToSession,
  composerHasContent,
  conversationIdFromHash,
  deleteRequest,
  formatRelativeTime,
  formatScheduleInterval,
  isUnresolvedPendingNewConversation,
  matchingOptimisticConversation,
  missingPendingConversationSummaries,
  pendingConversationDisplayId,
  pendingConversationStatus,
  promotePinnedConversationId,
  matchingPendingReplyMessageIndex,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  pendingConversationSends,
  pendingSendActivity,
  sidebarChatCountSummary,
  sidebarChatLastUserAt,
  sidebarChatMatchesFilters,
  sidebarChatMatchesSearch,
  sidebarSearchDelay,
  sidebarHealthNeedsRefresh,
  sidebarSelectedConversationId,
  selectedConversationAfterChatRefresh,
  sortSidebarChats,
  shouldRenderNewChatView,
  shouldShowStopAction,
  shouldProbeHistoricalActivity,
  shouldRefreshSelectedChat,
  postJsonRequest as postJson,
  isPostJsonTransportError,
  sidebarChatPreviewText,
  sidebarPreviewText,
  type PendingReply,
} from "./clientLogic";
import { RecentChatCache } from "./recentChatCache";
import { OfflineOutbox } from "./offlineOutbox";
import { appViewState, requestComposerFocus, requestSidebarTop } from "./appViewState.svelte";
import { copyText } from "./clipboard";
import { finePointer } from "./browserState.svelte";
import { appActions } from "./appActions.svelte";
import {
  closeSidebar,
  configureSidebar,
  openSidebar,
  sidebarListActions,
  sidebarListState,
  sidebarState,
} from "./sidebarState.svelte";
import { createConversationRenderer } from "./conversationRenderer";
import { imageAttachments, pendingImageAttachments } from "./conversationLogic";
import { getAttachmentPicker, getLogsPanel } from "./uiControllers";
import { createDeploymentMonitor } from "./deploymentMonitor";
import { createLiveUpdates } from "./liveUpdates";
import { createCompletionNotifications } from "./completionNotifications";
import {
  loadClientSessionId,
  loadComposerDrafts,
  loadPinnedIds,
  saveComposerDrafts,
  savePinnedIds,
} from "./clientStorage";

const clientScope = location.pathname.replace(/\/$/, "") || "/";
const recentChatCache = new RecentChatCache(clientScope, 20);
const offlineOutbox = new OfflineOutbox(clientScope);
const INITIAL_CHAT_LIST_LIMIT = 50;
const CHAT_LIST_PAGE_SIZE = 50;
const clientSessionId = loadClientSessionId();
let actionToastTimer: ReturnType<typeof setTimeout> | null = null;

type UiChat = {
  id: string;
  prompt?: string;
  status?: string;
  [key: string]: any;
};

const chatDetailRequests = new Map<string, Promise<UiChat | null>>();
const queuedPrefetches: Array<{ conversationId: string; revision: string }> = [];
const queuedPrefetchSet = new Set<string>();
const prefetchedChatRevisions = new Map<string, string>();
let chatPrefetchRunning = false;

function chatPrefetchRevision(chat: UiChat) {
  return JSON.stringify([chat.status || "", chat.updated_at ?? ""]);
}

function rememberPrefetchedRevision(conversationId: string, revision: string) {
  prefetchedChatRevisions.delete(conversationId);
  prefetchedChatRevisions.set(conversationId, revision);

  while (prefetchedChatRevisions.size > 50) {
    const oldest = prefetchedChatRevisions.keys().next().value;

    if (!oldest) break;

    prefetchedChatRevisions.delete(oldest);
  }
}

function fetchChatDetail(conversationId: string) {
  const existing = chatDetailRequests.get(conversationId);

  if (existing) return existing;

  const request = fetchJson(`api/chats/${encodeURIComponent(conversationId)}`, 30_000)
    .then((chat) => {
      if (!chat || String(chat.id || "") !== conversationId) return null;

      recentChatCache.remember(chat);

      return chat as UiChat;
    })
    .finally(() => {
      chatDetailRequests.delete(conversationId);
    });

  chatDetailRequests.set(conversationId, request);

  return request;
}

function runQueuedChatPrefetch() {
  if (chatPrefetchRunning) return;

  const pending = queuedPrefetches.shift();

  if (!pending) return;

  const { conversationId, revision } = pending;
  queuedPrefetchSet.delete(conversationId);
  chatPrefetchRunning = true;
  void fetchChatDetail(conversationId)
    .then((chat) => {
      if (chat) rememberPrefetchedRevision(conversationId, revision);
    })
    .catch((error) => {
      console.warn("Could not prefetch Prompta chat", conversationId, error);
    })
    .finally(() => {
      chatPrefetchRunning = false;

      if (!queuedPrefetches.length) return;

      const schedule =
        typeof requestIdleCallback === "function"
          ? (callback: () => void) => requestIdleCallback(callback, { timeout: 500 })
          : (callback: () => void) => setTimeout(callback, 40);
      schedule(runQueuedChatPrefetch);
    });
}

function queueChatPrefetch(chats: UiChat[]) {
  for (const chat of chats.slice(0, 8)) {
    const id = String(chat?.id || "");
    const revision = chatPrefetchRevision(chat);

    if (
      !id ||
      chat.status === "active" ||
      chat._optimisticNew ||
      chat._pending_send ||
      recentChatCache.getMemory(id) ||
      prefetchedChatRevisions.get(id) === revision ||
      queuedPrefetchSet.has(id) ||
      chatDetailRequests.has(id)
    ) {
      continue;
    }

    queuedPrefetchSet.add(id);
    queuedPrefetches.push({ conversationId: id, revision });
  }

  runQueuedChatPrefetch();
}

type UiPendingSend = PendingReply & {
  message: string;
  status: string;
  updatedAt: number;
  attachmentNames?: string[];
};

type UiState = {
  chats: UiChat[];
  selectedId: string | null;
  selectedUpdatedAt: number | string | null;
  selectedFingerprint: string;
  search: string;
  sidebarFingerprint: string;
  sidebarRenderedDate: string;
  mode: string;
  sending: boolean;
  stopping: boolean;
  composingNew: boolean;
  pendingNewId: string | null;
  pendingNewSend: UiPendingSend | null;
  pendingReplies: Map<string, PendingReply[]>;
  newChatFingerprint: string;
  selectedMetaFingerprint: string;
  chatsRequestId: number;
  chatOrderScope: string | null;
  chatListLimit: number;
  chatListHasMore: boolean;
  chatListLoadingMore: boolean;
  selectedRequestId: number;
  selectedChat: UiChat | null;
  selectedVisibleMessageCount: number;
  renderedConversationId: string;
  conversationViewports: Map<string, Record<string, unknown>>;
  chatSwitchToken: number;
  optimisticSequence: number;
  serverName: string;
  serverOnline: boolean | null;
  pinnedIds: Set<string>;
  composerDrafts: Map<string, string>;
  composerDraftTarget: string;
  activityProbes: Set<string>;
  activityProbeAt: Map<string, number>;
};

function persistPinChange(chatId: string, pinned: boolean) {
  void postJson("api/pins", { id: chatId, pinned }, 2, 5_000).catch((error) => {
    console.warn("Could not persist Prompta pin change", error);
  });
}

function persistPinPromotion(previousId: string, nextId: string) {
  if (!previousId || !nextId || previousId === nextId) return;

  void postJson("api/pins/promote", { from: previousId, to: nextId }, 2, 5_000).catch((error) => {
    console.warn("Could not persist Prompta pin promotion", error);
  });
}

function setChatPinned(chatId: string, pinned: boolean) {
  if (pinned) state.pinnedIds.add(chatId);
  else state.pinnedIds.delete(chatId);

  savePinnedIds(state.pinnedIds);
  persistPinChange(chatId, pinned);
  state.sidebarFingerprint = "";
}

function promotePendingConversationPin(pending, nextConversationId) {
  const previousId = pendingConversationDisplayId(pending);
  const changed = promotePinnedConversationId(state.pinnedIds, pending, nextConversationId);

  if (changed) {
    savePinnedIds(state.pinnedIds);
    persistPinPromotion(previousId, String(nextConversationId || ""));
    state.sidebarFingerprint = "";
  }

  return changed;
}

function promoteServerPendingPins(chats: UiChat[]) {
  let changed = false;

  for (const chat of chats) {
    const clientId = String(chat._client_id || "").trim();

    if (!chat._pending_send || !clientId) continue;

    const pending = { clientId };
    const previousId = pendingConversationDisplayId(pending);
    const nextId = String(chat.id || "");
    const promoted = promotePinnedConversationId(state.pinnedIds, pending, nextId);

    if (promoted) persistPinPromotion(previousId, nextId);

    changed = promoted || changed;
  }

  if (changed) {
    savePinnedIds(state.pinnedIds);
    state.sidebarFingerprint = "";
  }
}

const state: UiState = {
  chats: [],
  selectedId: null,
  selectedUpdatedAt: null,
  selectedFingerprint: "",
  search: "",
  sidebarFingerprint: "",
  sidebarRenderedDate: "",
  mode: "chats",
  sending: false,
  stopping: false,
  composingNew: false,
  pendingNewId: null,
  pendingNewSend: null,
  pendingReplies: new Map<string, PendingReply[]>(),
  newChatFingerprint: "",
  selectedMetaFingerprint: "",
  chatsRequestId: 0,
  chatOrderScope: null,
  chatListLimit: INITIAL_CHAT_LIST_LIMIT,
  chatListHasMore: false,
  chatListLoadingMore: false,
  selectedRequestId: 0,
  selectedChat: null,
  selectedVisibleMessageCount: 0,
  renderedConversationId: "",
  conversationViewports: new Map<string, Record<string, unknown>>(),
  chatSwitchToken: 0,
  optimisticSequence: 0,
  serverName: "",
  serverOnline: null,
  pinnedIds: loadPinnedIds(),
  composerDrafts: loadComposerDrafts(),
  composerDraftTarget: "",
  activityProbes: new Set(),
  activityProbeAt: new Map<string, number>(),
};

function markChatRead(chatId: string) {
  const chat = state.chats.find((candidate) => candidate.id === chatId);

  if (!chat?.unread) return;

  chat.unread = false;
  state.sidebarFingerprint = "";

  for (const group of sidebarListState.model.groups) {
    const row = group.chats.find((candidate) => candidate.id === chatId);

    if (row) {
      row.unread = false;
      break;
    }
  }

  void postJson(`api/chats/${encodeURIComponent(chatId)}/read`, {}, 2, 5_000).catch((error) => {
    console.warn("Could not persist Prompta read state", error);
  });
}

async function markAllChatsRead() {
  const unreadIds = new Set(
    state.chats.filter((chat) => Boolean(chat.unread)).map((chat) => chat.id),
  );

  for (const chat of state.chats) {
    if (unreadIds.has(chat.id)) chat.unread = false;
  }
  state.sidebarFingerprint = "";
  renderSidebar(true);

  try {
    await postJson("api/chats/read-all", {}, 2, 5_000);
  } catch (error) {
    for (const chat of state.chats) {
      if (unreadIds.has(chat.id)) chat.unread = true;
    }
    state.sidebarFingerprint = "";
    renderSidebar(true);
    console.warn("Could not mark all Prompta chats read", error);
  }
}

let sidebarRenderDeferred = false;

configureSidebar(() => {
  if (!sidebarRenderDeferred) return;

  sidebarRenderDeferred = false;
  renderSidebar();
});

const sidebar = {
  close: closeSidebar,
  open: openSidebar,
  isMoving: () => sidebarState.moving,
};

sidebarListActions.onSelect = (chatId, optimisticNew) => {
  if (optimisticNew && state.pendingNewSend) {
    renderNewChat();
    sidebar.close();

    return;
  }

  void selectChat(chatId);
};
sidebarListActions.onPin = (chatId) => {
  setChatPinned(chatId, !state.pinnedIds.has(chatId));
  renderSidebar(true);
  updatePinButton();
};
sidebarListActions.onPrefetch = (chatId) => {
  if (recentChatCache.getMemory(chatId)) return;

  void fetchChatDetail(chatId).catch(() => {});
};
sidebarListActions.onLoadMore = () => {
  void loadOlderChats();
};

const conversationRenderer = createConversationRenderer({
  onRetry: retryFailedSend,
  onBump: bumpPendingSend,
  onDelete: deletePendingSend,
  onEdit: editPendingSend,
});

const attachmentPicker = getAttachmentPicker();

attachmentPicker.configure({
  onChange: syncSendButton,
  setStatus: (message) => {
    appViewState.composerStatus = message;
  },
});

const logsPanel = getLogsPanel();

const deploymentMonitor = createDeploymentMonitor({
  onUpdateAvailable: () => {
    appViewState.updateAvailable = true;
  },
});

appActions.onApplyUpdate = () => {
  appViewState.updateApplying = true;
  void deploymentMonitor.applyUpdate();
};

const completionNotifications = createCompletionNotifications({
  displayServerName,
  getServerName: () => state.serverName,
  chatTitle,
});

const liveUpdates = createLiveUpdates({
  loadChats: () => loadChats(),
  loadServerIdentity: () => loadServerIdentity(),
  setServerStatus,
  observeHead: (head) => deploymentMonitor.observeHead(head),
  refreshDisplayedTimes,
  onStreamError: () => {
    appViewState.live = false;
  },
  onPageShow: () => deploymentMonitor.handleVisibilityChange(),
});

function composerDraftTarget() {
  if (state.composingNew) return "new";

  return state.selectedId ? "chat:" + state.selectedId : "";
}

function setStoredComposerDraft(target, value) {
  if (!target) return;

  const draft = String(value || "");

  if (draft) state.composerDrafts.set(target, draft);
  else state.composerDrafts.delete(target);

  saveComposerDrafts(state.composerDrafts);
}

function persistComposerDraft() {
  const target = composerDraftTarget();

  if (!target) return;

  state.composerDraftTarget = target;
  setStoredComposerDraft(target, appViewState.composerValue);
}

function clearComposerDraft(target = composerDraftTarget()) {
  if (!target) return;

  if (state.composerDrafts.delete(target)) saveComposerDrafts(state.composerDrafts);
}

function syncComposerDraftTarget() {
  const nextTarget = composerDraftTarget();

  if (nextTarget === state.composerDraftTarget) return;

  if (state.composerDraftTarget && !state.sending) {
    setStoredComposerDraft(state.composerDraftTarget, appViewState.composerValue);
  }

  state.composerDraftTarget = nextTarget;
  const draft = nextTarget ? state.composerDrafts.get(nextTarget) || "" : "";

  if (appViewState.composerValue !== draft) appViewState.composerValue = draft;

  syncSendButton();
}

function setComposerStatus(value) {
  appViewState.composerStatus = String(value ?? "");
}

function showActionToast(value) {
  const message = String(value ?? "");

  if (actionToastTimer !== null) {
    clearTimeout(actionToastTimer);
    actionToastTimer = null;
  }

  appViewState.actionToast = message;

  if (!message) return;

  actionToastTimer = setTimeout(() => {
    appViewState.actionToast = "";
    actionToastTimer = null;
  }, 2200);
}

function setCacheSummary(value) {
  appViewState.cacheSummary = String(value ?? "");
}

function showConversation(visible) {
  appViewState.emptyVisible = !visible;
  appViewState.conversationVisible = visible;
}

function setConversationHeading(title, meta) {
  appViewState.headingTitle = String(title ?? "");
  appViewState.headingMeta = String(meta ?? "");
}

function syncSendButton() {
  const waitingNew =
    state.composingNew &&
    state.pendingNewSend &&
    !["failed", "dead_lettered", "succeeded"].includes(state.pendingNewSend.status);
  const hasTarget = state.composingNew || Boolean(state.selectedId);
  const hasContent = composerHasContent(appViewState.composerValue, attachmentPicker.count());
  const canCompose = state.mode === "chats" && !appViewState.composerDisabled && hasTarget;
  const stopMode =
    canCompose && shouldShowStopAction(state.selectedChat?.status, state.composingNew, hasContent);
  const probingActivity = Boolean(state.selectedId && state.activityProbes.has(state.selectedId));

  appViewState.composerAction = stopMode ? "stop" : "send";
  appViewState.composerActionDisabled =
    !canCompose ||
    state.sending ||
    state.stopping ||
    probingActivity ||
    (!stopMode && (Boolean(waitingNew) || !hasContent));
}

function updateComposerActionButton() {
  syncSendButton();
}

function displayServerName(value) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  return raw
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function setServerStatus(server, online) {
  const raw = String(server || "").trim();

  if (raw) state.serverName = raw;

  if (typeof online === "boolean") state.serverOnline = online;

  const display = displayServerName(state.serverName || location.hostname);
  const knownOnline = state.serverOnline;
  appViewState.serverDisplay = display;
  appViewState.serverLabel =
    knownOnline === false ? "Server · " + display + " · offline" : "Server · " + display;
  appViewState.serverOnline = knownOnline;
  appViewState.live = knownOnline === true;
  appViewState.liveTitle =
    knownOnline === false
      ? display + " is offline"
      : knownOnline === true
        ? display + " is online"
        : display + " status unknown";
  logsPanel.setServerTitle(display);
}

function chatActivityAt(chat) {
  if (!chat) return 0;

  if (chat._optimisticNew || chat._optimisticReply || chat.status === "active") {
    return Number(chat.updated_at || chat.last_message_at || 0);
  }

  return Number(chat.last_message_at || chat.updated_at || 0);
}

function brokenChatLabel(chat) {
  const lastAssistantAt = chatLastAssistantAt(chat);

  if (lastAssistantAt) {
    return "broken · ChatGPT last responded " + formatRelativeTime(lastAssistantAt);
  }

  const referenceAt = chatBrokenReferenceAt(chat);

  return referenceAt
    ? "broken · no ChatGPT response · " + formatRelativeTime(referenceAt)
    : "broken";
}

function sameLocalDay(epochSeconds, offsetDays = 0) {
  if (!epochSeconds) return false;

  const d = new Date(epochSeconds * 1000);
  const target = new Date();
  target.setDate(target.getDate() - offsetDays);

  return (
    d.getFullYear() === target.getFullYear() &&
    d.getMonth() === target.getMonth() &&
    d.getDate() === target.getDate()
  );
}

function chatTitle(chat) {
  const title = (chat.title || "").replace(/^ChatGPT\s*[-–—:]?\s*/i, "").trim();

  if (title && title.toLowerCase() !== "chatgpt") return title;

  if (chat.job_name) return chat.job_name.replaceAll("-", " ");

  const preview = sidebarPreviewText(chat.preview);

  if (preview) return preview.slice(0, 72);

  return "Untitled conversation";
}

function truncate(value, length = 88) {
  const text = String(value || "")
    .replace(/\s+/g, " ")
    .trim();

  return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}

function sidebarGroupAt(chat) {
  return sidebarChatLastUserAt(chat);
}

function groupChats(chats: UiChat[]) {
  const ordered = sortSidebarChats(chats, state.pinnedIds);
  const pinned = ordered.filter((chat) => state.pinnedIds.has(chat.id));
  const unpinned = ordered.filter((chat) => !state.pinnedIds.has(chat.id));
  const groups: Array<[string, UiChat[]]> = [
    ["Pinned", pinned],
    ["Today", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat)))],
    ["Yesterday", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat), 1))],
    [
      "Previous",
      unpinned.filter(
        (chat) => !sameLocalDay(sidebarGroupAt(chat)) && !sameLocalDay(sidebarGroupAt(chat), 1),
      ),
    ],
  ];

  return groups.filter(([, items]) => items.length);
}

const iconStatusClasses = new Set([
  "active",
  "running",
  "succeeded",
  "complete",
  "cached",
  "local",
  "interrupted",
  "queued",
  "pending",
  "retrying",
  "failed",
  "broken",
  "dead_lettered",
  "live",
  "journal",
  "new",
  "idle",
]);

function setStatusIcon(status, label) {
  appViewState.syncStatus = iconStatusClasses.has(status) ? status : "neutral";
  appViewState.syncLabel = String(label || "");
}

function reconcileOptimisticNew(chats) {
  const pending = state.pendingNewSend;

  if (!pending) return;

  const knownConversationIds = new Set(state.chats.map((chat) => String(chat.id)));
  const matched = matchingOptimisticConversation(chats, pending, knownConversationIds);

  if (!matched) return;

  promotePendingConversationPin(pending, matched.id);
  pending.conversationId = matched.id;
  state.pendingNewId = matched.id;

  if (
    pending.status === "succeeded" &&
    !matched._pending_send &&
    !state.composingNew &&
    state.selectedId !== matched.id
  ) {
    state.pendingNewSend = null;
    state.pendingNewId = null;
  }
}

function sidebarChats(): UiChat[] {
  const displaySearch = appViewState.searchValue.trim();
  const searchScopeSettled = state.chatOrderScope === displaySearch;
  let chats: UiChat[] = state.chats.map((chat) => {
    const pending = state.pendingReplies.get(chat.id) || [];

    if (!pending.length) return chat;

    const latest = pending[pending.length - 1];

    return {
      ...chat,
      status: pendingConversationStatus(chat.status, latest.status),
      preview: latest.message,
      updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
      last_user_at: Math.max(
        Number(chat.last_user_at || chat.created_at || 0),
        Number(latest.createdAt || 0),
      ),
      _optimisticReply: true,
    };
  });

  if (displaySearch && !searchScopeSettled) {
    chats = chats.filter((chat) => sidebarChatMatchesSearch(chat, displaySearch));
  }

  chats.unshift(...missingPendingConversationSummaries(chats, state.pendingReplies, displaySearch));

  const pending = state.pendingNewSend;

  if (!pending) return chats;

  const matched = matchingOptimisticConversation(chats, pending);

  if (matched) {
    promotePendingConversationPin(pending, matched.id);
    pending.conversationId = matched.id;
    state.pendingNewId = matched.id;

    return chats;
  }

  const pendingId = pendingConversationDisplayId(pending);
  const optimistic = {
    id: pendingId,
    status: pendingConversationStatus("", pending.status),
    title: truncate(pending.message, 72) || "New chat",
    preview: pending.message,
    message_count: 1,
    job_name: "new chat",
    created_at: pending.createdAt,
    updated_at: pending.updatedAt,
    last_user_at: pending.createdAt,
    _optimisticNew: true,
  };
  const needle = displaySearch.toLowerCase();

  if (
    needle &&
    ![optimistic.title, optimistic.preview, optimistic.job_name].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(needle),
    )
  ) {
    return chats;
  }

  return [optimistic, ...chats];
}

function scrollSidebarToNewest() {
  requestSidebarTop();
}

function syncSidebarSelection() {
  const pendingNewDisplayId = state.composingNew
    ? pendingConversationDisplayId(state.pendingNewSend)
    : "";
  sidebarListState.selectedConversationId = sidebarSelectedConversationId(
    state.selectedId,
    state.composingNew,
    pendingNewDisplayId,
  );
}

function renderSidebar(force = false) {
  syncSidebarSelection();

  if (sidebar.isMoving()) {
    sidebarRenderDeferred = true;

    return;
  }

  const filtersActive = Object.values(appViewState.sidebarFilters).some(Boolean);
  const chats = sidebarChats().filter((chat) =>
    sidebarChatMatchesFilters(chat, appViewState.sidebarFilters),
  );
  const fingerprint =
    JSON.stringify(
      chats.map((chat) => [
        chat.id,
        chat.status,
        chat.title,
        sidebarChatPreviewText(chat.preview, chat.prompt),
        chat.message_count,
        chat.job_name,
        chatActivityAt(chat),
        chatIsBroken(chat),
        Boolean(chat._optimisticNew),
        Boolean(chat._optimisticReply),
        state.pinnedIds.has(chat.id),
        Boolean(chat.unread),
      ]),
    ) +
    JSON.stringify(appViewState.sidebarFilters) +
    String(state.chatListHasMore) +
    String(state.chatListLoadingMore) +
    new Date().toDateString();

  if (!force && fingerprint === state.sidebarFingerprint) return;

  state.sidebarFingerprint = fingerprint;
  state.sidebarRenderedDate = new Date().toDateString();

  if (!chats.length) {
    sidebarListState.model = {
      emptyState: filtersActive ? "filter" : state.search ? "search" : "empty",
      hasMore: state.chatListHasMore,
      loadingMore: state.chatListLoadingMore,
      groups: [],
    };

    return;
  }

  sidebarListState.model = {
    emptyState: "none",
    hasMore: state.chatListHasMore,
    loadingMore: state.chatListLoadingMore,
    groups: groupChats(chats).map(([label, groupedChats]) => ({
      label,
      chats: groupedChats.map((chat) => {
        const broken = chatIsBroken(chat);
        let statusClass: "active" | "complete" | "broken" | "neutral" | null = null;

        if (broken) {
          statusClass = "broken";
        } else if (chat.status !== "interrupted") {
          statusClass =
            chat.status === "active" || chat.status === "complete" ? chat.status : "neutral";
        }

        const activityAt = chatActivityAt(chat);

        return {
          id: chat.id,
          optimisticNew: Boolean(chat._optimisticNew),
          statusClass,
          broken,
          statusLabel: broken
            ? "No ChatGPT response for at least 40 minutes"
            : String(chat.status || "").toLowerCase() === "unattended"
              ? "Machine Gun Mode · result polling skipped"
              : String(chat.status || ""),
          title: String(chatTitle(chat)),
          preview: truncate(
            sidebarChatPreviewText(chat.preview, chat.prompt) || "Waiting for messages…",
          ),
          jobLabel: String(chat.job_name || String(chat.message_count || 0) + " messages"),
          activityAt,
          pinned: state.pinnedIds.has(chat.id),
          unread: Boolean(chat.unread),
        };
      }),
    })),
  };
}

function pendingReplyMessages(conversationId, cachedMessages) {
  const pending = pendingConversationSends(
    conversationId,
    state.pendingReplies.get(conversationId) || [],
    state.pendingNewSend,
  );
  const claimedCachedIndexes = new Set<number>();

  for (const item of pending) {
    const matchedIndex = matchingPendingReplyMessageIndex(
      cachedMessages,
      item,
      claimedCachedIndexes,
    );

    if (matchedIndex >= 0) {
      claimedCachedIndexes.add(matchedIndex);
      item.observedInCache = true;
      item.responseObservedInCache = cachedMessages
        .slice(matchedIndex + 1)
        .some((message) => message.role === "assistant" && !message.send_error);
      const cachedMessage = cachedMessages[matchedIndex];

      if (
        cachedMessage &&
        !imageAttachments(cachedMessage).length &&
        imageAttachments(item).length
      ) {
        cachedMessage.attachments = item.attachments;
      }
    }
  }
  // The cached user row is durable evidence that ChatGPT accepted the prompt,
  // so stop rendering the optimistic duplicate. Keep the ephemeral send job
  // only until an assistant row appears, so the activity indicator bridges the
  // gap between acceptance and the first visible response without offering a
  // duplicate Retry after durable acceptance.
  const remaining = pending.filter((item) => {
    if (!item.observedInCache) return true;

    if (item.responseObservedInCache) return false;

    return Boolean(
      pendingSendActivity(
        item.status,
        Boolean(item.sendId),
        item.retryAfterSeconds,
        item.retryAt,
        undefined,
        item.queuePosition,
        item.queueEtaAt,
        item.waitForResponse !== false,
      ),
    );
  });

  if (remaining.length) state.pendingReplies.set(conversationId, remaining);
  else state.pendingReplies.delete(conversationId);

  return remaining.flatMap((item) => {
    const messages: Record<string, unknown>[] = [];

    if (!item.observedInCache) {
      messages.push({
        message_key: `pending-user-${item.clientId || item.sendId}`,
        role: "user",
        content: item.message,
        attachments: item.attachments || [],
        status: "complete",
        updated_at: item.updatedAt,
        pending_bump_key:
          Number(item.queuePosition || 0) > 1 ? item.clientId || item.sendId || "" : "",
        pending_delete_key: item.clientId || item.sendId || "",
      });
    }

    const activity = pendingSendActivity(
      item.status,
      Boolean(item.sendId),
      item.retryAfterSeconds,
      item.retryAt,
      undefined,
      item.queuePosition,
      item.queueEtaAt,
      item.waitForResponse !== false,
    );

    if (activity) {
      messages.push({
        message_key: `pending-activity-${item.clientId || item.sendId}`,
        role: "assistant",
        content: "",
        status: "pending",
        updated_at: item.updatedAt,
        pending_activity: true,
        pending_activity_label: activity.label,
      });
    } else if (["failed", "dead_lettered"].includes(item.status || "")) {
      messages.push({
        message_key: `pending-error-${item.clientId || item.sendId}`,
        role: "assistant",
        content: `Send failed: ${item.error || "Unknown Prompta send error"}`,
        status: "complete",
        updated_at: item.updatedAt,
        send_error: true,
        retry_scope: "reply",
        retry_key: item.clientId || item.sendId || "",
      });
    }

    return messages;
  });
}

function updatePinButton() {
  const chatId = state.selectedId;
  const available = Boolean(chatId) && !state.composingNew;
  const pinned = Boolean(available && chatId && state.pinnedIds.has(chatId));
  appViewState.pinDisabled = !available;
  appViewState.pinActive = pinned;
  appViewState.pinLabel = pinned ? "Unpin chat" : "Pin chat";
}

function toggleSelectedPin() {
  const chatId = state.selectedId;

  if (!chatId || state.composingNew) return;

  setChatPinned(chatId, !state.pinnedIds.has(chatId));
  renderSidebar(true);
  updatePinButton();
}

function renderConversationMeta(chat, visibleMessageCount) {
  const title = chatTitle(chat);
  const broken = chatIsBroken(chat);
  const activityLabel = broken
    ? brokenChatLabel(chat)
    : chat.status === "active"
      ? "updating live"
      : chat.status === "interrupted"
        ? `interrupted · ${formatRelativeTime(chatActivityAt(chat))}`
        : formatRelativeTime(chatActivityAt(chat));
  const meta = [
    chat.job_name || "one-shot",
    `${visibleMessageCount} message${visibleMessageCount === 1 ? "" : "s"}`,
    activityLabel,
  ].join(" · ");
  const metaFingerprint = JSON.stringify([title, meta, chat.status, broken]);

  if (metaFingerprint === state.selectedMetaFingerprint) return;

  state.selectedMetaFingerprint = metaFingerprint;
  setConversationHeading(title, meta);
  const syncStatus = broken
    ? "broken"
    : chat.status === "active"
      ? "active"
      : chat.status === "interrupted"
        ? "interrupted"
        : "cached";
  const syncLabel = broken
    ? "No ChatGPT response for at least 40 minutes"
    : chat.status === "active"
      ? "Syncing from SQLite"
      : chat.status === "interrupted"
        ? "Last run was interrupted"
        : "Cached in SQLite";
  setStatusIcon(syncStatus, syncLabel);
}

function rememberConversationViewport(conversationId) {
  if (!conversationId || state.renderedConversationId !== conversationId) return;

  const snapshot = {
    ...conversationRenderer.captureConversationViewport(),
    anchorElement: null,
  };
  state.conversationViewports.delete(conversationId);
  state.conversationViewports.set(conversationId, snapshot);

  while (state.conversationViewports.size > 20) {
    const oldest = state.conversationViewports.keys().next().value;

    if (!oldest) break;

    state.conversationViewports.delete(oldest);
  }
}

function beginChatSwitch() {
  state.chatSwitchToken += 1;
  appViewState.chatSwitching = true;
}

function cancelChatSwitch() {
  state.chatSwitchToken += 1;
  appViewState.chatSwitching = false;
}

function finishChatSwitch(conversationId) {
  if (!appViewState.chatSwitching) return;

  const token = state.chatSwitchToken;
  requestAnimationFrame(() => {
    if (token !== state.chatSwitchToken || state.selectedId !== conversationId) return;

    appViewState.chatSwitching = false;
  });
}

function renderConversation(chat) {
  state.selectedChat = chat;
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  const visibleMessages = [...messages, ...pendingReplyMessages(chat.id, messages)];
  state.selectedVisibleMessageCount = visibleMessages.length;
  const allowStreaming = chat.status === "active";
  const fingerprint = JSON.stringify([
    chat.status,
    visibleMessages.map((message) => [
      message.message_key,
      conversationRenderer.messageNodeFingerprint(message, allowStreaming),
    ]),
  ]);

  if (fingerprint !== state.selectedFingerprint) {
    const isInitial = state.renderedConversationId !== chat.id;
    const rememberedViewport = isInitial ? state.conversationViewports.get(chat.id) : null;
    const viewportSnapshot =
      rememberedViewport || conversationRenderer.captureConversationViewport();
    state.selectedFingerprint = fingerprint;
    void conversationRenderer.renderMessageNodes(visibleMessages, allowStreaming);
    state.renderedConversationId = chat.id;
    conversationRenderer.restoreConversationViewport(
      viewportSnapshot,
      isInitial && !rememberedViewport,
    );
  }

  finishChatSwitch(chat.id);
  renderConversationMeta(chat, visibleMessages.length);
  appViewState.emptyVisible = false;
  appViewState.conversationVisible = true;
  appViewState.composerDisabled = false;
  state.composingNew = false;
  syncSidebarSelection();
  syncComposerDraftTarget();
  syncSendButton();
  appViewState.shareDisabled = false;
  updatePinButton();
  syncSendButton();
  const pendingActivity = [...(state.pendingReplies.get(chat.id) || [])]
    .reverse()
    .map((item) =>
      pendingSendActivity(
        item.status,
        Boolean(item.sendId),
        item.retryAfterSeconds,
        item.retryAt,
        undefined,
        item.queuePosition,
        item.queueEtaAt,
        item.waitForResponse !== false,
      ),
    )
    .find(Boolean);

  if (pendingActivity) {
    appViewState.composerStatus = pendingActivity.statusText;
  } else if (!state.sending) {
    appViewState.composerStatus =
      chat.status === "active"
        ? "Uses the existing live ChatGPT tab."
        : chat.status === "interrupted"
          ? "The last run was interrupted. Sending will reopen this chat."
          : "Sending will reopen this chat once if its retained tab has expired.";
  }
}

function showMode(mode) {
  state.mode = mode === "logs" ? "logs" : mode === "prompta" ? "prompta" : "chats";
  appViewState.mode =
    state.mode === "logs" ? "logs" : state.mode === "prompta" ? "prompta" : "chats";
  const logsMode = state.mode === "logs";
  const promptaMode = state.mode === "prompta";

  if (logsMode) {
    cancelChatSwitch();
    state.selectedMetaFingerprint = "";
    const display = displayServerName(state.serverName || location.hostname);
    setConversationHeading(
      display + " Prompta logs",
      "journalctl · prompta-ui.service · " + display,
    );
    setStatusIcon("journal", display + " journal");
    appViewState.composerDisabled = true;
    appViewState.shareDisabled = true;
    appViewState.composerStatus = "Switch back to chats to send a message.";
    updateComposerActionButton();

    return;
  }

  if (promptaMode) {
    cancelChatSwitch();
    state.selectedMetaFingerprint = "";
    setConversationHeading("Prompta", "Machine Gun Mode · scheduled jobs");
    setStatusIcon("local", "Prompta controls");
    appViewState.composerDisabled = true;
    appViewState.shareDisabled = true;
    appViewState.pinDisabled = true;
    appViewState.pinActive = false;
    appViewState.composerStatus = "";
    updateComposerActionButton();

    return;
  }

  if (state.selectedId) {
    void loadSelectedChat();
  } else if (state.composingNew) {
    renderNewChat();
  } else {
    clearConversation();
  }
}

function clearConversation() {
  cancelChatSwitch();
  state.composingNew = false;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  state.renderedConversationId = "";
  syncSidebarSelection();
  appViewState.emptyVisible = true;
  appViewState.conversationVisible = false;
  void conversationRenderer.renderMessageNodes([], false);
  setConversationHeading("Prompta", "Local conversation history");
  setStatusIcon("local", "Local cache");
  appViewState.composerDisabled = true;
  appViewState.shareDisabled = true;
  updatePinButton();
  appViewState.composerPlaceholder = "Message Prompta…";
  appViewState.composerStatus = "";
  syncComposerDraftTarget();
  updateComposerActionButton();
}

function renderNewChat() {
  cancelChatSwitch();
  const enteringNewChat = !state.composingNew;
  state.composingNew = true;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  state.renderedConversationId = "";
  state.mode = "chats";
  appViewState.mode = "chats";
  syncSidebarSelection();
  syncComposerDraftTarget();
  const pending = state.pendingNewSend;
  const waiting = pending && !["failed", "dead_lettered", "succeeded"].includes(pending.status);
  const fingerprint = JSON.stringify([
    pending?.sendId || "",
    pending?.message || "",
    pending?.status || "",
    pending?.error || "",
    pending?.conversationId || "",
    pending?.retryAfterSeconds || 0,
    pending?.retryAt || 0,
    pending?.retryAttempt || 0,
    pending?.queuePosition || 0,
    pending?.queueEtaAt || 0,
    imageAttachments(pending).map((attachment) => [
      attachment.id || "",
      attachment.name || "",
      attachment.type || "",
      String(attachment.src || "").length,
    ]),
  ]);

  if (shouldRenderNewChatView(enteringNewChat, fingerprint, state.newChatFingerprint)) {
    state.newChatFingerprint = fingerprint;

    if (pending) {
      const messages: any[] = [
        {
          message_key: `pending-user-${pending.clientId || pending.sendId}`,
          role: "user",
          content: pending.message,
          attachments: pending.attachments || [],
          status: "complete",
          updated_at: pending.updatedAt,
          pending_bump_key:
            Number(pending.queuePosition || 0) > 1 ? pending.clientId || pending.sendId || "" : "",
          pending_delete_key: pending.clientId || pending.sendId || "",
        },
      ];
      const activity = pendingSendActivity(
        pending.status,
        Boolean(pending.sendId),
        pending.retryAfterSeconds,
        pending.retryAt,
        undefined,
        pending.queuePosition,
        pending.queueEtaAt,
        pending.waitForResponse !== false,
      );

      if (activity) {
        messages.push({
          message_key: `pending-activity-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: "",
          status: "pending",
          updated_at: pending.updatedAt,
          pending_activity: true,
          pending_activity_label: activity.label,
        });
      } else if (["failed", "dead_lettered"].includes(pending.status)) {
        messages.push({
          message_key: `pending-error-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: `Send failed: ${pending.error || "Unknown Prompta send error"}`,
          status: "complete",
          updated_at: pending.updatedAt,
          send_error: true,
          retry_scope: "new",
          retry_key: pending.clientId || pending.sendId,
        });
      }

      const viewportSnapshot = conversationRenderer.captureConversationViewport();
      showConversation(true);
      void conversationRenderer.renderMessageNodes(messages, true);
      conversationRenderer.restoreConversationViewport(viewportSnapshot, enteringNewChat);
    } else {
      showConversation(false);
      void conversationRenderer.renderMessageNodes([], false);
    }

    setConversationHeading(
      "New chat",
      pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation",
    );
    setStatusIcon(pending ? "queued" : "new", pending ? "Send queued" : "Fresh conversation");
    appViewState.composerDisabled = false;
    syncSendButton();
    appViewState.shareDisabled = true;
    updatePinButton();
    appViewState.composerPlaceholder = "Start a new chat…";
    const activity = pending
      ? pendingSendActivity(
          pending.status,
          Boolean(pending.sendId),
          pending.retryAfterSeconds,
          pending.retryAt,
          undefined,
          pending.queuePosition,
          pending.queueEtaAt,
          pending.waitForResponse !== false,
        )
      : null;
    setComposerStatus(
      pending
        ? ["failed", "dead_lettered"].includes(pending.status)
          ? pending.status === "dead_lettered"
            ? "Send exhausted its retry budget. Retry to enqueue it again."
            : "Send failed. The error is shown in the chat."
          : activity?.statusText || "Sent. Waiting for the cached response…"
        : "",
    );
  }

  updateComposerActionButton();

  if (enteringNewChat) {
    appViewState.mode = "chats";
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    renderSidebar();
    scrollSidebarToNewest();
    sidebar.close();

    if (!waiting && finePointer.current) {
      requestComposerFocus();
    }
  }
}

async function fetchJson(url, timeoutMs = 10_000, controller = new AbortController()) {
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function hydratePinnedIds() {
  const cachedIds = new Set(state.pinnedIds);

  try {
    let payload = await fetchJson("api/pins", 2_000);

    if (!payload?.initialized && cachedIds.size) {
      payload = await postJson("api/pins/seed", { ids: Array.from(cachedIds) }, 1, 2_000);
    }

    if (!payload?.initialized || !Array.isArray(payload.ids)) return;

    state.pinnedIds = new Set(payload.ids.map((id) => String(id || "").trim()).filter(Boolean));
    savePinnedIds(state.pinnedIds);
    state.sidebarFingerprint = "";
  } catch (error) {
    console.warn("Could not hydrate Prompta pins; using browser cache", error);
  }
}

async function hydrateRecentChatCache() {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const cached = await Promise.race([
    Promise.all([recentChatCache.warm(), recentChatCache.warmSummaries()]),
    new Promise<null>((resolve) => {
      timeout = setTimeout(() => resolve(null), 500);
    }),
  ]);

  if (timeout !== undefined) clearTimeout(timeout);

  if (!cached) return false;

  const [cachedChats, cachedSummaries] = cached;
  const sidebarSnapshot = cachedSummaries.length ? cachedSummaries : cachedChats;

  if (!sidebarSnapshot.length || state.search) return false;

  const unique = new Map();

  for (const chat of sidebarSnapshot) {
    if (chat?.id && !unique.has(chat.id)) unique.set(chat.id, chat);
  }

  state.chats = sortSidebarChats(Array.from(unique.values()), state.pinnedIds);
  state.chatOrderScope = "";
  const activeCount = state.chats.filter((chat) => chat.status === "active").length;
  setCacheSummary(sidebarChatCountSummary(state.chats.length, activeCount, state.search));
  const hashId = conversationIdFromHash(location.hash);
  const initialId = hashId || state.chats[0]?.id || "";

  if (initialId) {
    state.selectedId = initialId;
    const chat = recentChatCache.getMemory(initialId);

    if (chat) {
      state.selectedUpdatedAt = chat.updated_at;
      renderConversation(chat);
    } else {
      conversationRenderer.renderLoadingState();
      showConversation(true);
    }
  }

  renderSidebar();

  return true;
}

async function loadServerIdentity() {
  try {
    const payload = await fetchJson("api/health");

    setServerStatus(payload.server, payload.online);
    appViewState.unattended = payload.unattended === true;
    appViewState.unattendedSendGapSeconds = Number(payload.send_gap_seconds || 60);
    const head = String(payload.head || "")
      .trim()
      .toLowerCase();
    deploymentMonitor.observeHead(head);
    appViewState.headLabel = head ? head : "unknown";
    appViewState.headTitle = head ? "UI commit " + head : "UI commit unavailable";
  } catch (error) {
    setServerStatus(state.serverName || location.hostname, false);
    console.warn("Could not load Prompta server identity", error);
  }
}

async function toggleUnattendedMode() {
  if (appViewState.unattendedUpdating) return;

  const next = !appViewState.unattended;
  appViewState.unattendedUpdating = true;
  try {
    const payload = await postJson("api/mode", { unattended: next }, 1, 10_000);
    appViewState.unattended = payload.unattended === true;
    appViewState.unattendedSendGapSeconds = Number(payload.send_gap_seconds || 60);
    showActionToast(
      appViewState.unattended
        ? "Machine Gun Mode on · no result polling · " +
            appViewState.unattendedSendGapSeconds +
            "s send gap"
        : "Machine Gun Mode off · normal result polling restored",
    );
  } catch (error) {
    showActionToast(
      "Could not change Machine Gun Mode: " + String(error).replace(/^Error:\s*/, ""),
    );
  } finally {
    appViewState.unattendedUpdating = false;
  }
}

async function hydratePendingSends() {
  try {
    const payload = await fetchJson("api/sends");
    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];

    for (const job of jobs) {
      const status = String(job.status || "queued");
      const sendId = String(job.send_id || "");

      if (!sendId || ["succeeded", "failed", "dead_lettered"].includes(status)) continue;

      const conversationId = String(job.conversation_id || "");
      const pending: UiPendingSend = {
        sendId,
        clientId: String(job.client_id || ""),
        message: String(job.message || ""),
        status,
        error: String(job.error || ""),
        conversationId,
        origin: job.operation === "once" ? "new" : "reply",
        createdAt: Number(job.created_at || Date.now() / 1000),
        updatedAt: Number(job.updated_at || Date.now() / 1000),
        retryAfterSeconds: Number(job.retry_after_seconds || 0),
        retryAt: Number(job.retry_at || 0),
        retryAttempt: Number(job.retry_attempt || 0),
        queuePosition: Number(job.queue_position || 0),
        queueEtaAt: Number(job.queue_eta_at || 0),
        attachmentNames: Array.isArray(job.attachment_names)
          ? job.attachment_names.map((value) => String(value))
          : [],
      };

      if (job.operation === "reply" && conversationId) {
        const items = state.pendingReplies.get(conversationId) || [];

        if (!items.some((item) => item.sendId === sendId)) {
          items.push(pending);
          items.sort((left, right) => Number(left.createdAt || 0) - Number(right.createdAt || 0));
          state.pendingReplies.set(conversationId, items);
        }

        void watchSend(sendId, false, conversationId);
      } else if (
        job.operation === "once" &&
        !conversationId &&
        !state.pendingNewSend &&
        clientIdBelongsToSession(pending.clientId, clientSessionId)
      ) {
        state.pendingNewSend = pending;
        state.composingNew = true;
        void watchSend(sendId, true, "");
      }
    }
  } catch (error) {
    console.warn("Could not hydrate pending Prompta sends", error);
  }
}

let chatsRequestController: AbortController | null = null;

async function loadOlderChats() {
  if (state.chatListLoadingMore || !state.chatListHasMore || state.chatListLimit >= 500) return;

  state.chatListLoadingMore = true;
  state.chatListLimit = Math.min(500, state.chatListLimit + CHAT_LIST_PAGE_SIZE);
  state.sidebarFingerprint = "";
  renderSidebar(true);

  try {
    await loadChats();
  } finally {
    state.chatListLoadingMore = false;
    state.sidebarFingerprint = "";
    renderSidebar(true);
  }
}

async function loadChats(forceSelectedRefresh = false) {
  const requestId = ++state.chatsRequestId;
  chatsRequestController?.abort();
  const requestController = new AbortController();
  chatsRequestController = requestController;

  try {
    const payload = await fetchJson(
      chatListRequestUrl(state.search, state.pinnedIds, state.chatListLimit),
      10_000,
      requestController,
    );

    if (requestId !== state.chatsRequestId) return;

    const chats = payload.chats || [];
    state.chatListHasMore = Boolean(payload.has_more);
    promoteServerPendingPins(chats);
    reconcileOptimisticNew(chats);
    const orderedChats = sortSidebarChats(chats, state.pinnedIds);

    if (!state.search) {
      recentChatCache.rememberSummaries(orderedChats);
      queueChatPrefetch(orderedChats);
    }

    completionNotifications.trackCompletions(chats);
    state.chats = orderedChats;
    state.chatOrderScope = state.search;
    const activeCount = state.chats.filter((chat) => chat.status === "active").length;

    setCacheSummary(sidebarChatCountSummary(state.chats.length, activeCount, state.search));
    const hashId = conversationIdFromHash(location.hash);

    if (!state.selectedId && hashId) {
      // Deep links must work even when the conversation is older than the
      // sidebar's bounded /api/chats result set.
      state.selectedId = hashId;
    }

    state.selectedId = selectedConversationAfterChatRefresh(
      state.selectedId,
      state.composingNew,
      state.chats,
    );

    renderSidebar();

    if (state.mode === "chats") {
      if (state.selectedId) {
        const summary = state.chats.find((chat) => chat.id === state.selectedId);
        const shouldRefresh = shouldRefreshSelectedChat(
          summary,
          state.selectedUpdatedAt,
          state.selectedFingerprint,
          forceSelectedRefresh,
        );

        if (shouldRefresh) await loadSelectedChat();
      } else if (!state.composingNew) {
        clearConversation();
      }
    }
  } catch (error) {
    if (requestId !== state.chatsRequestId) return;

    appViewState.live = false;
    setCacheSummary("Cache unavailable");
    console.error(error);
  } finally {
    if (chatsRequestController === requestController) chatsRequestController = null;
  }
}

const HISTORICAL_ACTIVITY_PROBE_TTL_MS = 30_000;

async function probeHistoricalActivity(conversationId) {
  if (
    appViewState.unattended ||
    !conversationId ||
    !shouldProbeHistoricalActivity(state.selectedChat?.status)
  )
    return;

  const now = Date.now();
  const lastProbeAt = Number(state.activityProbeAt.get(conversationId) || 0);

  if (
    state.activityProbes.has(conversationId) ||
    now - lastProbeAt < HISTORICAL_ACTIVITY_PROBE_TTL_MS
  )
    return;

  state.activityProbeAt.set(conversationId, now);
  state.activityProbes.add(conversationId);

  if (state.selectedId === conversationId) {
    setComposerStatus("Refreshing cached conversation state…");
    syncSendButton();
  }

  try {
    const payload = await postJson(
      "api/chats/" + encodeURIComponent(conversationId) + "/probe",
      {},
      1,
      30_000,
    );

    if (state.selectedId !== conversationId || state.mode !== "chats") return;

    const chat = payload?.chat;

    if (!chat || chat.id !== conversationId) return;

    state.selectedUpdatedAt = chat.updated_at;
    recentChatCache.remember(chat);
    renderConversation(chat);
    await loadChats();
  } catch (error) {
    if (state.selectedId === conversationId) {
      setComposerStatus("Could not refresh the cached conversation state.");
    }

    console.warn("Could not refresh historical chat state", error);
  } finally {
    state.activityProbes.delete(conversationId);

    if (state.selectedId === conversationId) syncSendButton();
  }
}

function renderRecentChatSnapshot(conversationId) {
  if (!conversationId || state.mode !== "chats") return;

  const memoryChat = recentChatCache.getMemory(conversationId);

  if (memoryChat) {
    state.selectedUpdatedAt = memoryChat.updated_at;
    renderConversation(memoryChat);

    return;
  }

  if (!state.renderedConversationId) {
    conversationRenderer.renderLoadingState();
    showConversation(true);
  }

  void recentChatCache.get(conversationId).then((chat) => {
    if (
      !chat ||
      state.mode !== "chats" ||
      state.selectedId !== conversationId ||
      state.selectedChat?.id === conversationId
    )
      return;

    state.selectedUpdatedAt = chat.updated_at;
    renderConversation(chat);
  });
}

async function loadSelectedChat() {
  if (!state.selectedId || state.mode !== "chats") return;

  const selectedId = state.selectedId;

  if (!state.selectedChat || state.selectedChat.id !== selectedId) {
    renderRecentChatSnapshot(selectedId);
  }

  const requestId = ++state.selectedRequestId;

  try {
    const chat = await fetchChatDetail(selectedId);

    if (
      !chat ||
      requestId !== state.selectedRequestId ||
      selectedId !== state.selectedId ||
      chat.id !== state.selectedId
    )
      return;

    if (state.pendingNewId === chat.id && !state.pendingNewSend) {
      state.pendingNewId = null;
    }

    state.selectedUpdatedAt = chat.updated_at;
    recentChatCache.remember(chat);
    renderConversation(chat);
    markChatRead(chat.id);

    if (shouldProbeHistoricalActivity(chat.status)) {
      void probeHistoricalActivity(chat.id);
    }
  } catch (error) {
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId) return;

    const missing = String(error).startsWith("Error: 404");

    if (missing && state.pendingNewId !== state.selectedId) {
      void recentChatCache.remove(selectedId);

      if (conversationIdFromHash(location.hash) === selectedId) {
        history.replaceState(null, "", `${location.pathname}${location.search}`);
      }

      clearConversation();
    }

    if (!missing || state.pendingNewId !== state.selectedId) console.error(error);

    finishChatSwitch(selectedId);
  }
}

async function selectChat(id) {
  if (!id) return;

  if (state.mode !== "chats") showMode("chats");

  // Start dismissing the mobile sidebar before any chat fetch or sidebar render.
  // The previous ordering made a tap feel network-bound because closeSidebar()
  // did not run until /api/chats/:id completed.
  sidebar.close();

  if (isUnresolvedPendingNewConversation(state.pendingNewSend, id)) {
    rememberConversationViewport(state.selectedId);
    state.pendingNewId = state.pendingNewSend?.conversationId || null;
    renderNewChat();

    return;
  }

  markChatRead(id);

  if (id === state.selectedId) {
    if (!state.selectedChat || state.selectedChat.id !== id) {
      await loadSelectedChat();
    }

    return;
  }

  rememberConversationViewport(state.selectedId);
  beginChatSwitch();
  const pendingNew = state.pendingNewSend?.conversationId === id ? state.pendingNewSend : null;
  state.composingNew = false;
  state.pendingNewId = pendingNew ? id : null;
  appViewState.composerPlaceholder = "Message Prompta…";
  state.selectedId = id;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
  syncSidebarSelection();
  await loadSelectedChat();
}

let searchTimer;

appActions.onSearch = (value) => {
  appViewState.searchValue = value;
  const search = value.trim();
  state.sidebarFingerprint = "";
  renderSidebar(true);
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (state.search === search && state.chatOrderScope === search) return;

    state.search = search;
    state.chatListLimit = INITIAL_CHAT_LIST_LIMIT;
    state.chatListHasMore = false;
    state.sidebarFingerprint = "";
    void loadChats();
  }, sidebarSearchDelay(search));
};

appActions.onSidebarFilter = (filter) => {
  appViewState.sidebarFilters[filter] = !appViewState.sidebarFilters[filter];
  state.sidebarFingerprint = "";
  renderSidebar(true);
};

appActions.onMarkAllRead = () => {
  void markAllChatsRead();
};

appActions.onNewChat = () => {
  state.pendingNewSend = null;
  state.newChatFingerprint = "";
  renderNewChat();
};

async function runScheduleSlashCommand(command, originalMessage) {
  state.sending = true;
  appViewState.composerDisabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  appViewState.composerValue = "";
  updateComposerActionButton();
  setComposerStatus("Saving schedule…");

  try {
    const result = await postJson("api/schedule", {
      interval_minutes: command.intervalMinutes,
      prompt: command.prompt,
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    const interval = formatScheduleInterval(Number(result.interval_minutes));
    const prefix = result.created === false ? "Already scheduled" : "Scheduled";
    setComposerStatus(prefix + " on " + server + ": every " + interval + " · " + command.prompt);
  } catch (error) {
    appViewState.composerValue = originalMessage;
    persistComposerDraft();
    setComposerStatus("Schedule failed: " + String(error).replace(/^Error:\s*/, ""));
    console.error(error);
  } finally {
    state.sending = false;
    appViewState.composerDisabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();

    if (finePointer.current) requestComposerFocus();
  }
}

async function runAtSlashCommand(command, originalMessage) {
  state.sending = true;
  appViewState.composerDisabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  appViewState.composerValue = "";
  updateComposerActionButton();
  setComposerStatus("Saving one-time schedule…");

  try {
    const result = await postJson("api/schedule-at", {
      run_at_epoch: command.runAtEpoch,
      prompt: command.prompt,
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    setComposerStatus(
      "Scheduled on " + server + ": " + command.runAtLabel + " · " + command.prompt,
    );
  } catch (error) {
    appViewState.composerValue = originalMessage;
    persistComposerDraft();
    setComposerStatus("Schedule failed: " + String(error).replace(/^Error:\s*/, ""));
    console.error(error);
  } finally {
    state.sending = false;
    appViewState.composerDisabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();

    if (finePointer.current) requestComposerFocus();
  }
}

function pendingReply(conversationId, sendId) {
  return (state.pendingReplies.get(conversationId) || []).find((item) => item.sendId === sendId);
}

function updatePendingReply(conversationId, sendId, updates) {
  const item = pendingReply(conversationId, sendId);

  if (!item) return false;

  const previous = JSON.stringify([
    item.status || "",
    item.error || "",
    item.retryAfterSeconds || 0,
    item.retryAt || 0,
    item.retryAttempt || 0,
    item.queuePosition || 0,
    item.queueEtaAt || 0,
  ]);
  Object.assign(item, updates);

  const changed =
    JSON.stringify([
      item.status || "",
      item.error || "",
      item.retryAfterSeconds || 0,
      item.retryAt || 0,
      item.retryAttempt || 0,
      item.queuePosition || 0,
      item.queueEtaAt || 0,
    ]) !== previous;

  if (changed) item.updatedAt = Date.now() / 1000;

  return changed;
}

function setPendingDeleteBusy(deleteKey: string, busy: boolean) {
  conversationRenderer.setPendingDeleteBusy(deleteKey, busy);
}

async function bumpPendingSend(bumpKey: string) {
  let pending: PendingReply | null = null;
  const conversationId = state.selectedId || "";

  if (
    state.pendingNewSend &&
    (state.pendingNewSend.clientId === bumpKey || state.pendingNewSend.sendId === bumpKey)
  ) {
    pending = state.pendingNewSend;
  } else if (conversationId) {
    pending =
      (state.pendingReplies.get(conversationId) || []).find(
        (item) => item.clientId === bumpKey || item.sendId === bumpKey,
      ) || null;
  }

  if (!pending) return;

  const sendId = String(pending.sendId || "");

  if (!sendId) {
    setComposerStatus("Message is still entering the queue. Try sending it next again.");

    return;
  }

  try {
    const job = await postJson("api/sends/" + encodeURIComponent(sendId) + "/bump", {});
    pending.queuePosition = Number(job.queue_position || 1);
    pending.queueEtaAt = Number(job.queue_eta_at || 0);
    pending.updatedAt = Date.now() / 1000;

    if (state.pendingNewSend === pending && state.composingNew) renderNewChat();
    else if (state.selectedChat?.id === conversationId) {
      state.selectedFingerprint = "";
      renderConversation(state.selectedChat);
    }

    setComposerStatus("Queued message moved to the front.");
  } catch (error) {
    console.warn("Could not bump pending Prompta send", error);
    setComposerStatus("Could not move the pending message to the front.");
  }
}

async function deletePendingSend(deleteKey: string) {
  let pending: PendingReply | null = null;
  let creatingNew = false;
  const conversationId = state.selectedId || "";

  if (
    state.pendingNewSend &&
    (state.pendingNewSend.clientId === deleteKey || state.pendingNewSend.sendId === deleteKey)
  ) {
    pending = state.pendingNewSend;
    creatingNew = true;
  } else if (conversationId) {
    pending =
      (state.pendingReplies.get(conversationId) || []).find(
        (item) => item.clientId === deleteKey || item.sendId === deleteKey,
      ) || null;
  }

  if (!pending) return;

  const sendId = String(pending.sendId || "");

  const canDiscardLocally =
    !sendId && ["failed", "dead_lettered"].includes(String(pending.status || ""));

  if (!sendId && !canDiscardLocally) {
    setComposerStatus("Message is still entering the queue. Try deleting again.");

    return;
  }

  if (sendId) {
    setPendingDeleteBusy(deleteKey, true);

    try {
      await deleteRequest("api/sends/" + encodeURIComponent(sendId));
    } catch (error) {
      setPendingDeleteBusy(deleteKey, false);
      console.warn("Could not delete pending Prompta send", error);
      setComposerStatus("Could not delete the pending message.");

      return;
    }
  }

  if (creatingNew) {
    if (state.pendingNewSend === pending) {
      state.pendingNewSend = null;
      state.pendingNewId = null;
      state.newChatFingerprint = "";
    }
  } else {
    const items = state.pendingReplies.get(conversationId) || [];
    const remaining = items.filter((item) => item !== pending);

    if (remaining.length) state.pendingReplies.set(conversationId, remaining);
    else state.pendingReplies.delete(conversationId);

    if (state.selectedId === conversationId) state.selectedFingerprint = "";
  }

  if (creatingNew && state.composingNew) renderNewChat();
  else if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);

  renderSidebar();
}

async function editPendingSend(editKey: string) {
  let pending: PendingReply | null = null;
  let creatingNew = false;
  const conversationId = state.selectedId || "";

  if (
    state.pendingNewSend &&
    (state.pendingNewSend.clientId === editKey || state.pendingNewSend.sendId === editKey)
  ) {
    pending = state.pendingNewSend;
    creatingNew = true;
  } else if (conversationId) {
    pending =
      (state.pendingReplies.get(conversationId) || []).find(
        (item) => item.clientId === editKey || item.sendId === editKey,
      ) || null;
  }

  if (!pending) return;

  const sendId = String(pending.sendId || "");

  if (!sendId) {
    setComposerStatus("Message is still entering the queue. Try editing again.");

    return;
  }

  try {
    await deleteRequest("api/sends/" + encodeURIComponent(sendId));
  } catch (error) {
    console.warn("Could not cancel pending Prompta send for editing", error);
    setComposerStatus("Could not edit the pending message.");

    return;
  }

  if (creatingNew) {
    state.pendingNewSend = null;
    state.pendingNewId = null;
    state.newChatFingerprint = "";
    state.composingNew = true;
    renderNewChat();
  } else {
    const items = state.pendingReplies.get(conversationId) || [];
    const remaining = items.filter((item) => item !== pending);

    if (remaining.length) state.pendingReplies.set(conversationId, remaining);
    else state.pendingReplies.delete(conversationId);

    state.selectedFingerprint = "";

    if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
  }

  appViewState.composerValue = pending.message || "";
  persistComposerDraft();
  syncSendButton();
  renderSidebar();

  const attachmentNames = (pending as UiPendingSend).attachmentNames || [];

  if (attachmentNames.length) {
    setComposerStatus("Editing pending message. Reattach the files before sending.");
  } else {
    setComposerStatus("Editing pending message.");
  }

  requestComposerFocus(true);
}

async function watchSend(sendId, creatingNew, conversationId) {
  let statusFailures = 0;

  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    let job;

    try {
      job = await fetchJson(`api/sends/${encodeURIComponent(sendId)}`);
      statusFailures = 0;
    } catch {
      statusFailures += 1;

      // A failed status read is not evidence that the send itself failed. The
      // UI server may have restarted or the connection may only be transient;
      // offering Retry here can duplicate a prompt that ChatGPT is still
      // processing. Reconcile against the cache and keep observing instead.
      if (statusFailures >= 3) {
        await loadChats();

        if (creatingNew) {
          const pending = state.pendingNewSend;

          if (!pending || pending.sendId !== sendId) return;

          if (pending.conversationId && state.composingNew && state.mode === "chats") {
            state.composingNew = false;
            state.selectedId = pending.conversationId;
            state.pendingNewId = pending.conversationId;
            history.replaceState(null, "", `#/${encodeURIComponent(pending.conversationId)}`);
            await loadSelectedChat();

            return;
          }
        } else {
          if (!pendingReply(conversationId, sendId)) return;

          if (state.selectedId === conversationId) await loadSelectedChat();

          if (!pendingReply(conversationId, sendId)) return;
        }

        setComposerStatus(
          "Send status unavailable. Prompta may still be running it; reconnecting…",
        );
      }

      await new Promise((resolve) => setTimeout(resolve, Math.min(5000, 250 * statusFailures)));
      continue;
    }

    const status = job.status || "running";

    if (creatingNew) {
      const pendingNewSend = state.pendingNewSend;

      if (!pendingNewSend || pendingNewSend.sendId !== sendId) return;

      const nextError = job.error || "";
      const nextConversationId = job.conversation_id || pendingNewSend.conversationId || "";
      const nextRetryAfterSeconds = Number(job.retry_after_seconds || 0);
      const nextRetryAt = Number(job.retry_at || 0);
      const nextRetryAttempt = Number(job.retry_attempt || 0);
      const nextQueuePosition = Number(job.queue_position || 0);
      const nextQueueEtaAt = Number(job.queue_eta_at || 0);

      if (nextConversationId) {
        promotePendingConversationPin(pendingNewSend, nextConversationId);
      }

      const changed =
        pendingNewSend.status !== status ||
        pendingNewSend.error !== nextError ||
        pendingNewSend.conversationId !== nextConversationId ||
        pendingNewSend.retryAfterSeconds !== nextRetryAfterSeconds ||
        pendingNewSend.retryAt !== nextRetryAt ||
        pendingNewSend.retryAttempt !== nextRetryAttempt ||
        pendingNewSend.queuePosition !== nextQueuePosition ||
        pendingNewSend.queueEtaAt !== nextQueueEtaAt;
      Object.assign(pendingNewSend, {
        status,
        error: nextError,
        conversationId: nextConversationId,
        retryAfterSeconds: nextRetryAfterSeconds,
        retryAt: nextRetryAt,
        retryAttempt: nextRetryAttempt,
        queuePosition: nextQueuePosition,
        queueEtaAt: nextQueueEtaAt,
      });

      if (changed) pendingNewSend.updatedAt = Date.now() / 1000;

      if (status === "succeeded") {
        const newId = job.conversation_id;

        if (!newId) {
          pendingNewSend.status = "failed";
          pendingNewSend.error = "Prompta reported success without a conversation id";

          if (state.composingNew) renderNewChat();

          return;
        }

        const completedPending = pendingNewSend;
        completedPending.waitForResponse = !appViewState.unattended;
        promotePendingConversationPin(completedPending, newId);
        completedPending.conversationId = newId;
        state.pendingNewId = newId;
        const pendingReplies = state.pendingReplies.get(newId) || [];

        if (!pendingReplies.some((item) => item.clientId === completedPending.clientId)) {
          pendingReplies.push(completedPending);
          state.pendingReplies.set(newId, pendingReplies);
        }

        state.pendingNewSend = null;
        const stillViewingPending = state.composingNew && state.mode === "chats";

        if (!stillViewingPending) {
          renderSidebar();
          await loadChats();

          return;
        }

        state.composingNew = false;
        state.selectedId = newId;
        history.replaceState(null, "", `#/${encodeURIComponent(newId)}`);
        appViewState.composerPlaceholder = "Message Prompta…";
        setComposerStatus(
          completedPending.waitForResponse
            ? "Sent. Waiting for the cached response…"
            : "Sent. Machine Gun Mode will not read the result.",
        );
        state.selectedUpdatedAt = null;
        await loadChats();
        await loadSelectedChat();

        return;
      }

      if (["failed", "dead_lettered"].includes(status)) {
        if (state.composingNew) renderNewChat();

        renderSidebar();

        return;
      }

      if (changed) {
        if (state.composingNew) renderNewChat();

        renderSidebar();
      }

      continue;
    }

    const changed = updatePendingReply(conversationId, sendId, {
      status,
      error: job.error || "",
      retryAfterSeconds: Number(job.retry_after_seconds || 0),
      retryAt: Number(job.retry_at || 0),
      retryAttempt: Number(job.retry_attempt || 0),
      queuePosition: Number(job.queue_position || 0),
      queueEtaAt: Number(job.queue_eta_at || 0),
    });

    if (changed) renderSidebar();

    if (status === "succeeded") {
      const completedReply = pendingReply(conversationId, sendId);
      if (completedReply) completedReply.waitForResponse = !appViewState.unattended;
    }

    if (state.selectedId === conversationId) await loadSelectedChat();

    if (status === "succeeded") {
      setComposerStatus(
        appViewState.unattended
          ? "Sent. Machine Gun Mode will not read the result."
          : "Sent. Waiting for the cached response…",
      );
      await loadChats();

      return;
    }

    if (["failed", "dead_lettered"].includes(status)) {
      setComposerStatus(
        status === "dead_lettered"
          ? "Send exhausted its retry budget. Retry to enqueue it again."
          : "Send failed. The error is shown in the chat.",
      );

      return;
    }
  }
}

async function retryFailedSend(scope, retryKey) {
  if (!retryKey || state.sending) return;

  let pending: PendingReply | null = null;

  if (scope === "new") {
    if (
      state.pendingNewSend &&
      (state.pendingNewSend.clientId === retryKey || state.pendingNewSend.sendId === retryKey)
    ) {
      pending = state.pendingNewSend;
      state.pendingNewSend = null;
      state.newChatFingerprint = "";
      state.composingNew = true;
      renderNewChat();
    }
  } else if (scope === "reply" && state.selectedId) {
    const selectedId = state.selectedId;
    const items = state.pendingReplies.get(selectedId) || [];
    pending = items.find((item) => item.clientId === retryKey || item.sendId === retryKey) || null;

    if (pending) {
      const remaining = items.filter((item) => item !== pending);

      if (remaining.length) state.pendingReplies.set(selectedId, remaining);
      else state.pendingReplies.delete(selectedId);

      state.selectedFingerprint = "";

      if (state.selectedChat?.id === state.selectedId) renderConversation(state.selectedChat);
    }
  }

  if (!pending) return;

  appViewState.composerValue = pending.message || "";
  syncSendButton();

  if (((pending as UiPendingSend).attachmentNames || []).length) {
    setComposerStatus("Reattach the files, then send again.");
    requestComposerFocus();

    return;
  }

  await sendSelectedMessage();
}

async function stopSelectedChat() {
  const conversationId = state.selectedId;

  if (!conversationId || state.mode !== "chats" || state.stopping) return;

  state.stopping = true;
  syncSendButton();
  setComposerStatus("Stopping response…");

  try {
    await postJson("api/chats/" + encodeURIComponent(conversationId) + "/stop", {});
    setComposerStatus("Stopped.");
    state.selectedFingerprint = "";
    state.selectedUpdatedAt = null;
    await loadSelectedChat();
    await loadChats();
  } catch (error) {
    setComposerStatus("Stop failed: " + String(error).replace(/^Error:\s*/, ""));
    console.error(error);
  } finally {
    state.stopping = false;
    syncSendButton();
  }
}

async function sendSelectedMessage() {
  const message = appViewState.composerValue.trim();
  const creatingNew = state.composingNew;
  const conversationId = state.selectedId;
  const attachments = attachmentPicker.snapshot();

  if (!message || state.mode !== "chats" || state.sending) return;

  if (message.toLowerCase() === "/logs") {
    clearComposerDraft();
    appViewState.composerValue = "";
    showMode("logs");

    return;
  }

  if (["/list", "/jobs"].includes(message.toLowerCase())) {
    showMode("prompta");

    return;
  }

  void completionNotifications.requestPermissionFromGesture();
  const scheduleCommand = parseScheduleSlashCommand(message);

  if (scheduleCommand) {
    if (attachments.length) {
      setComposerStatus("Scheduled prompts do not include attachments.");

      return;
    }

    if ("error" in scheduleCommand) {
      setComposerStatus(scheduleCommand.error);

      return;
    }

    await runScheduleSlashCommand(scheduleCommand, message);

    return;
  }

  const atCommand = parseAtSlashCommand(message);

  if (atCommand) {
    if (attachments.length) {
      setComposerStatus("Scheduled prompts do not include attachments.");

      return;
    }

    if ("error" in atCommand) {
      setComposerStatus(atCommand.error);

      return;
    }

    await runAtSlashCommand(atCommand, message);

    return;
  }

  if (!creatingNew && isUnresolvedPendingNewConversation(state.pendingNewSend, conversationId)) {
    state.pendingNewId = state.pendingNewSend?.conversationId || null;
    renderNewChat();
    setComposerStatus("Wait for the pending chat to start before sending another message.");

    return;
  }

  if (!creatingNew && !conversationId) return;

  let serializedAttachments: Array<{ name: string; type: string; data: string }> = [];

  if (attachments.length) {
    state.sending = true;
    appViewState.composerDisabled = true;
    appViewState.composerActionDisabled = true;
    attachmentPicker.setDisabled(true);
    setComposerStatus("Preparing attachments…");

    try {
      serializedAttachments = await attachmentPicker.serialize();
    } catch (error) {
      state.sending = false;
      appViewState.composerDisabled = false;
      attachmentPicker.setDisabled(false);
      syncSendButton();
      setComposerStatus("Attachment failed: " + String(error).replace(/^Error:\s*/, ""));

      return;
    }

    state.sending = false;
  }

  const now = Date.now() / 1000;
  const pending: UiPendingSend = {
    sendId: "",
    clientId: `${clientSessionId}:${Date.now()}-${++state.optimisticSequence}`,
    message,
    status: "queued",
    error: "",
    conversationId: conversationId || "",
    origin: creatingNew ? "new" : "reply",
    createdAt: now,
    updatedAt: now,
    attachmentNames: attachments.map((file) => file.name),
    attachments: pendingImageAttachments(serializedAttachments),
  };
  state.sending = true;
  appViewState.composerActionDisabled = true;
  clearComposerDraft();
  appViewState.composerValue = "";

  if (creatingNew) {
    state.pendingNewSend = pending;
    state.newChatFingerprint = "";
    renderNewChat();
    renderSidebar();
    scrollSidebarToNewest();
  } else {
    const targetConversationId = conversationId || "";
    const items = state.pendingReplies.get(targetConversationId) || [];
    items.push(pending);
    state.pendingReplies.set(targetConversationId, items);
    state.selectedFingerprint = "";

    if (state.selectedChat?.id === targetConversationId) renderConversation(state.selectedChat);

    renderSidebar();
  }

  try {
    const result = creatingNew
      ? await postJson(
          "api/chats",
          { message, attachments: serializedAttachments, client_id: pending.clientId },
          attachments.length ? 1 : 3,
        )
      : await postJson(
          `api/chats/${encodeURIComponent(conversationId || "")}/messages`,
          { message, attachments: serializedAttachments, client_id: pending.clientId },
          attachments.length ? 1 : 3,
        );

    if (!result.send_id) throw new Error("Prompta did not return a send id");

    const coalescedReply = !creatingNew
      ? (state.pendingReplies.get(conversationId || "") || []).find(
          (item) => item !== pending && item.sendId === result.send_id,
        )
      : null;

    if (coalescedReply) {
      const coalescedUiReply = coalescedReply as UiPendingSend;
      coalescedReply.message = [coalescedReply.message, pending.message].filter(Boolean).join("\n");
      coalescedUiReply.attachmentNames = [
        ...(coalescedUiReply.attachmentNames || []),
        ...(pending.attachmentNames || []),
      ];
      coalescedReply.attachments = [
        ...(coalescedReply.attachments || []),
        ...(pending.attachments || []),
      ];
      coalescedReply.status = result.status || "queued";
      coalescedReply.queuePosition = Number(result.queue_position || 0);
      coalescedReply.queueEtaAt = Number(result.queue_eta_at || 0);
      coalescedReply.updatedAt = Date.now() / 1000;
      state.pendingReplies.set(
        conversationId || "",
        (state.pendingReplies.get(conversationId || "") || []).filter((item) => item !== pending),
      );

      if (attachments.length) attachmentPicker.clear();

      state.selectedFingerprint = "";

      if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);

      renderSidebar();

      return;
    }

    pending.sendId = result.send_id;
    pending.status = result.status || "queued";
    pending.queuePosition = Number(result.queue_position || 0);
    pending.queueEtaAt = Number(result.queue_eta_at || 0);
    pending.updatedAt = Date.now() / 1000;

    if (attachments.length) attachmentPicker.clear();

    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
    } else {
      state.selectedFingerprint = "";

      if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
    }

    renderSidebar();
    void watchSend(result.send_id, creatingNew, conversationId);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    let savedOffline = false;

    if (isPostJsonTransportError(error)) {
      try {
        await offlineOutbox.enqueue({
          operation: creatingNew ? "new_chat" : "reply",
          targetChatId: creatingNew ? null : conversationId || null,
          message,
          attachments: serializedAttachments,
          clientId: String(pending.clientId || ""),
          createdAt: now * 1000,
          lastError: errorMessage,
        });
        savedOffline = true;

        if (attachments.length) attachmentPicker.clear();
      } catch (outboxError) {
        console.error("Could not persist failed post to the offline outbox", outboxError);
      }
    }

    pending.status = "failed";
    pending.error = savedOffline ? "Saved offline for retry." : errorMessage;
    pending.updatedAt = Date.now() / 1000;

    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
    } else {
      state.selectedFingerprint = "";

      if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
    }

    renderSidebar();
    console.error(error);
  } finally {
    state.sending = false;

    if (attachments.length) attachmentPicker.setDisabled(false);

    if (!creatingNew && state.selectedId && state.mode === "chats") {
      appViewState.composerDisabled = false;
      syncSendButton();

      if (finePointer.current) requestComposerFocus();
    } else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
      appViewState.composerDisabled = false;
      syncSendButton();

      if (finePointer.current) requestComposerFocus();
    }

    updateComposerActionButton();
  }
}

async function copySelectedChatUrl() {
  if (!state.selectedId) return;

  const url = new URL(location.href);
  url.hash = "/" + encodeURIComponent(state.selectedId);
  const copied = await copyText(url.toString());
  const message = copied ? "Chat link copied." : "Could not copy the chat link.";
  setComposerStatus(message);
  showActionToast(message);
}

appActions.onPin = toggleSelectedPin;
appActions.onShare = () => void copySelectedChatUrl();
appActions.onPromptaPage = () => showMode("prompta");
appActions.onUnattendedMode = () => void toggleUnattendedMode();

appActions.onSubmit = () => {
  if (appViewState.composerAction === "stop") void stopSelectedChat();
  else void sendSelectedMessage();
};

appActions.onComposerInput = (value) => {
  appViewState.composerValue = value;
  persistComposerDraft();
  syncSendButton();
};

appActions.onHashChange = () => {
  const id = conversationIdFromHash(location.hash);

  if (id && id !== state.selectedId) void selectChat(id);
};

appActions.onPageHide = () => liveUpdates.handlePageHide();
appActions.onPageShow = () => liveUpdates.handlePageShow();

function refreshDisplayedTimes() {
  appViewState.clockTick = Math.floor(Date.now() / 60_000) * 60_000;

  if (
    state.composingNew &&
    (["rate_limited", "retrying"].includes(state.pendingNewSend?.status || "") ||
      (state.pendingNewSend?.status === "queued" &&
        Number(state.pendingNewSend?.queueEtaAt || 0) > 0))
  ) {
    state.newChatFingerprint = "";
    renderNewChat();
  } else if (
    state.selectedId &&
    (state.pendingReplies.get(state.selectedId) || []).some(
      (item) =>
        ["rate_limited", "retrying"].includes(item.status || "") ||
        (item.status === "queued" && Number(item.queueEtaAt || 0) > 0),
    )
  ) {
    state.selectedFingerprint = "";
    void loadSelectedChat();
  }

  const sidebarRows = sidebarListState.model.groups.flatMap((group) => group.chats);
  const currentDate = new Date().toDateString();

  if (
    currentDate !== state.sidebarRenderedDate ||
    sidebarHealthNeedsRefresh(
      sidebarRows,
      sidebarChats(),
      appViewState.sidebarFilters.broken,
      appViewState.clockTick / 1000,
    )
  ) {
    renderSidebar(true);
  }

  if (
    state.mode === "chats" &&
    state.selectedChat &&
    state.selectedChat.id === state.selectedId &&
    !state.composingNew
  ) {
    state.selectedMetaFingerprint = "";
    renderConversationMeta(state.selectedChat, state.selectedVisibleMessageCount);
  }
}

async function startApp() {
  deploymentMonitor.registerServiceWorker();
  void loadServerIdentity();
  await hydratePinnedIds();
  await hydratePendingSends();
  const hydrated = await hydrateRecentChatCache();

  if (!hydrated) {
    conversationRenderer.renderLoadingState();
    showConversation(true);
  }

  appViewState.bootComplete = true;
  await loadChats(true);
  liveUpdates.start();
}

void startApp();
