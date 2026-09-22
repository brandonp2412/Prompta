import { mount } from "svelte";
import SidebarList from "./SidebarList.svelte";

import {
  chatListRequestUrl,
  clientIdBelongsToSession,
  composerHasContent,
  conversationIdFromHash,
  deleteRequest,
  formatScheduleInterval,
  matchingOptimisticConversation,
  missingPendingConversationSummaries,
  pendingConversationDisplayId,
  promotePinnedConversationId,
  matchingPendingReplyMessageIndex,
  messageAgeText,
  nextSlashCommandIndex,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  pendingConversationSends,
  pendingSendActivity,
  sidebarChatCountSummary,
  sidebarChatCreatedAt,
  sidebarChatIsSelected,
  sidebarSelectedConversationId,
  selectedConversationAfterChatRefresh,
  sortSidebarChats,
  shouldRenderNewChatView,
  shouldShowStopAction,
  shouldProbeHistoricalActivity,
  shouldRefreshSelectedChat,
  postJsonRequest as postJson,
  sidebarChatPreviewText,
  sidebarPreviewText,
  type PendingReply,
} from "./clientLogic";
import { RecentChatCache } from "./recentChatCache";
import { createJobsDialog } from "./jobsDialog";
import { createSidebar } from "./sidebar";
import {
  createConversationRenderer,
  imageAttachments,
  pendingImageAttachments,
} from "./conversationRenderer";
import { createAttachmentPicker } from "./attachmentPicker";
import { createLogsPanel } from "./logsPanel";
import { createDeploymentMonitor } from "./deploymentMonitor";
import { createLiveUpdates } from "./liveUpdates";
import { createCompletionNotifications } from "./completionNotifications";
import { createChangelogDialog } from "./changelogDialog";
import {
  loadClientSessionId,
  loadComposerDrafts,
  loadPinnedIds,
  saveComposerDrafts,
  savePinnedIds,
} from "./clientStorage";

const recentChatCache = new RecentChatCache(location.pathname.replace(/\/$/, "") || "/", 20);
const clientSessionId = loadClientSessionId();

type UiChat = {
  id: string;
  prompt?: string;
  status?: string;
  [key: string]: any;
};

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

function syncViewportHeight() {
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${Math.round(viewportHeight)}px`);
}

syncViewportHeight();

window.setTimeout(() => document.documentElement.classList.remove("booting"), 1200);

window.addEventListener("resize", syncViewportHeight);

window.visualViewport?.addEventListener("resize", syncViewportHeight);

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);

  if (!element) throw new Error(`Missing required UI element: ${selector}`);

  return element;
}

const els = {
  chatList: requiredElement<HTMLElement>("#chatList"),
  sidebarScroll: requiredElement<HTMLElement>(".sidebar-scroll"),
  searchInput: requiredElement<HTMLInputElement>("#searchInput"),
  conversation: requiredElement<HTMLElement>("#conversation"),
  emptyState: requiredElement<HTMLElement>("#emptyState"),
  viewport: requiredElement<HTMLElement>("#conversationViewport"),
  chatHeading: requiredElement<HTMLElement>("#chatHeading"),
  syncLabel: requiredElement<HTMLElement>("#syncLabel"),
  cacheSummary: requiredElement<HTMLElement>("#cacheSummary"),
  headLabel: requiredElement<HTMLElement>("#headLabel"),
  versionUpdateNotice: requiredElement<HTMLButtonElement>("#versionUpdateNotice"),
  globalLiveOrb: requiredElement<HTMLElement>("#globalLiveOrb"),
  serverLabel: requiredElement<HTMLElement>("#serverLabel"),
  newChatButton: requiredElement<HTMLButtonElement>("#newChatButton"),
  pinChatButton: requiredElement<HTMLButtonElement>("#pinChatButton"),
  shareChatButton: requiredElement<HTMLButtonElement>("#shareChatButton"),
  slashMenu: requiredElement<HTMLElement>("#slashMenu"),
  composerFooter: requiredElement<HTMLElement>("#composerFooter"),
  messageForm: requiredElement<HTMLFormElement>("#messageForm"),
  messageInput: requiredElement<HTMLTextAreaElement>("#messageInput"),
  sendButton: requiredElement<HTMLButtonElement>("#sendButton"),
  composerStatus: requiredElement<HTMLElement>("#composerStatus"),
};

let sidebarRenderDeferred = false;

const sidebar = createSidebar({
  onMotionEnd: () => {
    if (!sidebarRenderDeferred) return;

    sidebarRenderDeferred = false;
    renderSidebar();
  },
});

const sidebarList = mount(SidebarList, {
  target: els.chatList,
  props: {
    onSelect: (chatId: string, optimisticNew: boolean) => {
      if (optimisticNew && state.pendingNewSend) {
        renderNewChat();
        sidebar.close();

        return;
      }

      void selectChat(chatId);
    },
    onPin: (chatId: string) => {
      setChatPinned(chatId, !state.pinnedIds.has(chatId));
      renderSidebar(true);
      updatePinButton();
    },
  },
});

const jobsDialog = createJobsDialog({
  closeSidebar: sidebar.close,
  resizeComposer,
  syncSendButton,
});

const conversationRenderer = createConversationRenderer({
  onRetry: retryFailedSend,
  onDelete: deletePendingSend,
  onEdit: editPendingSend,
});

const attachmentPicker = createAttachmentPicker({
  onChange: syncSendButton,
  setStatus: (message) => setTextIfChanged(els.composerStatus, message),
});

const logsPanel = createLogsPanel({
  fetchJson: (url, timeoutMs) => fetchJson(url, timeoutMs),
  formatRelativeTime,
});

const deploymentMonitor = createDeploymentMonitor({
  onUpdateAvailable: () => {
    els.versionUpdateNotice.hidden = false;
  },
});

els.versionUpdateNotice.addEventListener("click", () => {
  els.versionUpdateNotice.disabled = true;
  els.versionUpdateNotice.textContent = "Updating…";
  els.versionUpdateNotice.setAttribute("aria-label", "Updating Prompta");
  void deploymentMonitor.applyUpdate();
});

createChangelogDialog({
  fetchJson: (url, timeoutMs) => fetchJson(url, timeoutMs),
  closeSidebar: sidebar.close,
});

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
  onStreamError: () => els.globalLiveOrb.classList.remove("live"),
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
  setStoredComposerDraft(target, els.messageInput.value);
}

function clearComposerDraft(target = composerDraftTarget()) {
  if (!target) return;

  if (state.composerDrafts.delete(target)) saveComposerDrafts(state.composerDrafts);
}

function syncComposerDraftTarget() {
  const nextTarget = composerDraftTarget();

  if (nextTarget === state.composerDraftTarget) return;

  if (state.composerDraftTarget && !state.sending) {
    setStoredComposerDraft(state.composerDraftTarget, els.messageInput.value);
  }

  state.composerDraftTarget = nextTarget;
  const draft = nextTarget ? state.composerDrafts.get(nextTarget) || "" : "";

  if (els.messageInput.value !== draft) els.messageInput.value = draft;

  resizeComposer();
  updateSlashMenu();
  syncSendButton();
}

function setTextIfChanged(element: Element, value) {
  const text = String(value ?? "");

  if (element.textContent !== text) element.textContent = text;
}

function setHiddenIfChanged(element: HTMLElement, hidden) {
  if (element.hidden !== hidden) element.hidden = hidden;
}

function patchDomNode(current, next) {
  if (
    current.nodeType !== next.nodeType ||
    (current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName)
  ) {
    const replacement = next.cloneNode(true);
    current.replaceWith(replacement);

    return replacement;
  }

  if (current.nodeType === Node.TEXT_NODE) {
    if (current.data !== next.data) current.data = next.data;

    return current;
  }

  if (current.nodeType !== Node.ELEMENT_NODE) return current;

  const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
  const detailsOpen = preserveDetailsOpen ? (current as HTMLDetailsElement).open : false;

  for (const attribute of Array.from(current.attributes as NamedNodeMap) as Attr[]) {
    if (preserveDetailsOpen && attribute.name === "open") continue;

    if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
  }

  for (const attribute of Array.from(next.attributes as NamedNodeMap) as Attr[]) {
    if (preserveDetailsOpen && attribute.name === "open") continue;

    if (current.getAttribute(attribute.name) !== attribute.value) {
      current.setAttribute(attribute.name, attribute.value);
    }
  }

  patchDomChildren(current, next);

  if (preserveDetailsOpen) (current as HTMLDetailsElement).open = detailsOpen;

  return current;
}

function domPatchKey(node) {
  if (!node || node.nodeType !== Node.ELEMENT_NODE) return "";

  return (node as HTMLElement).dataset.domKey || "";
}

function patchDomChildren(currentParent, nextParent) {
  let index = 0;

  while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
    let current = currentParent.childNodes[index];
    const next = nextParent.childNodes[index];

    if (!next) {
      current.remove();
      continue;
    }

    if (!current) {
      currentParent.append(next.cloneNode(true));
      index += 1;
      continue;
    }

    const nextKey = domPatchKey(next);

    if (nextKey && domPatchKey(current) !== nextKey) {
      const match = Array.from(currentParent.childNodes)
        .slice(index + 1)
        .find((candidate) => domPatchKey(candidate) === nextKey);

      if (match) {
        currentParent.insertBefore(match, current);
        current = match;
      } else {
        currentParent.insertBefore(next.cloneNode(true), current);
        index += 1;
        continue;
      }
    }

    patchDomNode(current, next);
    index += 1;
  }
}

function patchHtmlChildren(element: Element, html: string) {
  const template = document.createElement("template");
  template.innerHTML = html;
  patchDomChildren(element, template.content);
}

function setConversationHeading(title, meta) {
  let titleNode = els.chatHeading.querySelector(".heading-title");
  let metaNode = els.chatHeading.querySelector(".heading-meta");

  if (!titleNode) {
    titleNode = document.createElement("div");
    titleNode.className = "heading-title";
    els.chatHeading.prepend(titleNode);
  }

  if (!metaNode) {
    metaNode = document.createElement("div");
    metaNode.className = "heading-meta";
    els.chatHeading.append(metaNode);
  }

  setTextIfChanged(titleNode, title);
  setTextIfChanged(metaNode, meta);
}

const SEND_ICON =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';

const STOP_ICON =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7.5" y="7.5" width="9" height="9" rx="1.5" fill="currentColor" stroke="none"/></svg>';

function syncSendButton() {
  const waitingNew =
    state.composingNew &&
    state.pendingNewSend &&
    !["failed", "dead_lettered", "succeeded"].includes(state.pendingNewSend.status);
  const hasTarget = state.composingNew || Boolean(state.selectedId);
  const hasContent = composerHasContent(els.messageInput.value, attachmentPicker.count());
  const canCompose = state.mode === "chats" && !els.messageInput.disabled && hasTarget;
  const stopMode =
    canCompose && shouldShowStopAction(state.selectedChat?.status, state.composingNew, hasContent);
  const probingActivity = Boolean(state.selectedId && state.activityProbes.has(state.selectedId));
  const action = stopMode ? "stop" : "send";

  if (els.sendButton.dataset.action !== action) {
    els.sendButton.dataset.action = action;
    patchHtmlChildren(els.sendButton, stopMode ? STOP_ICON : SEND_ICON);
    els.sendButton.setAttribute("aria-label", stopMode ? "Stop response" : "Send message");
    els.sendButton.title = stopMode ? "Stop response" : "Send message";
  }

  els.sendButton.disabled =
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
  setTextIfChanged(
    els.serverLabel,
    knownOnline === false ? `Server · ${display} · offline` : `Server · ${display}`,
  );
  document.title = `Prompta · ${display}`;
  logsPanel.setServerTitle(display);
  const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');

  if (appleTitle) appleTitle.setAttribute("content", `Prompta ${display}`);

  els.globalLiveOrb.classList.toggle("live", knownOnline === true);
  els.globalLiveOrb.title =
    knownOnline === false
      ? `${display} is offline`
      : knownOnline === true
        ? `${display} is online`
        : `${display} status unknown`;
}

function formatRelativeTime(epochSeconds) {
  if (!epochSeconds) return "";

  const delta = Date.now() - epochSeconds * 1000;
  const abs = Math.abs(delta);

  if (abs < 45_000) return "now";

  if (abs < 3_600_000) return `${Math.max(1, Math.round(abs / 60_000))}m`;

  if (abs < 86_400_000) return `${Math.round(abs / 3_600_000)}h`;

  if (abs < 604_800_000) return `${Math.round(abs / 86_400_000)}d`;

  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    new Date(epochSeconds * 1000),
  );
}

function chatActivityAt(chat) {
  if (!chat) return 0;

  if (chat._optimisticNew || chat._optimisticReply || chat.status === "active") {
    return Number(chat.updated_at || chat.last_message_at || 0);
  }

  return Number(chat.last_message_at || chat.updated_at || 0);
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
  return sidebarChatCreatedAt(chat);
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
  "dead_lettered",
  "live",
  "journal",
  "new",
  "idle",
]);

function setStatusIcon(element, status, label, kind = "") {
  const statusClassName = iconStatusClasses.has(status) ? status : "neutral";
  element.className = ["status-icon", kind, statusClassName].filter(Boolean).join(" ");
  element.title = label;
  element.setAttribute("aria-label", label);
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
  const chats: UiChat[] = state.chats.map((chat) => {
    const pending = state.pendingReplies.get(chat.id) || [];

    if (!pending.length) return chat;

    const latest = pending[pending.length - 1];

    return {
      ...chat,
      status: ["failed", "dead_lettered"].includes(latest.status || "") ? chat.status : "active",
      preview: latest.message,
      updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
      _optimisticReply: true,
    };
  });
  chats.unshift(...missingPendingConversationSummaries(chats, state.pendingReplies, state.search));

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
    status: ["failed", "dead_lettered"].includes(pending.status) ? pending.status : "active",
    title: truncate(pending.message, 72) || "New chat",
    preview: pending.message,
    message_count: 1,
    job_name: "new chat",
    created_at: pending.createdAt,
    updated_at: pending.updatedAt,
    _optimisticNew: true,
  };
  const needle = state.search.trim().toLowerCase();

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
  if (els.sidebarScroll.scrollTop) els.sidebarScroll.scrollTop = 0;
}

function renderSidebar(force = false) {
  if (sidebar.isMoving()) {
    sidebarRenderDeferred = true;

    return;
  }

  const chats = sidebarChats();
  const pendingNewDisplayId = state.composingNew
    ? pendingConversationDisplayId(state.pendingNewSend)
    : "";
  const selectionId = sidebarSelectedConversationId(
    state.selectedId,
    state.composingNew,
    pendingNewDisplayId,
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
        Boolean(chat._optimisticNew),
        Boolean(chat._optimisticReply),
        state.pinnedIds.has(chat.id),
      ]),
    ) +
    new Date().toDateString() +
    selectionId;

  if (!force && fingerprint === state.sidebarFingerprint) return;

  state.sidebarFingerprint = fingerprint;

  if (!chats.length) {
    sidebarList.update({
      emptyState: state.search ? "search" : "empty",
      groups: [],
    });

    return;
  }

  sidebarList.update({
    emptyState: "none",
    groups: groupChats(chats).map(([label, groupedChats]) => ({
      label,
      chats: groupedChats.map((chat) => {
        const selected = sidebarChatIsSelected(
          chat,
          state.selectedId,
          state.composingNew,
          pendingNewDisplayId,
        );
        let statusClass: "active" | "complete" | "neutral" | null = null;

        if (chat.status !== "interrupted") {
          statusClass =
            chat.status === "active" || chat.status === "complete" ? chat.status : "neutral";
        }

        const activityAt = chatActivityAt(chat);

        return {
          id: chat.id,
          selected,
          optimisticNew: Boolean(chat._optimisticNew),
          statusClass,
          title: String(chatTitle(chat)),
          preview: truncate(
            sidebarChatPreviewText(chat.preview, chat.prompt) || "Waiting for messages…",
          ),
          jobLabel: String(chat.job_name || String(chat.message_count || 0) + " messages"),
          activityAt,
          relativeTime: formatRelativeTime(activityAt),
          pinned: state.pinnedIds.has(chat.id),
        };
      }),
    })),
  });
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
  els.pinChatButton.disabled = !available;
  els.pinChatButton.classList.toggle("active", Boolean(pinned));
  els.pinChatButton.setAttribute("aria-pressed", String(Boolean(pinned)));
  const label = pinned ? "Unpin chat" : "Pin chat";
  els.pinChatButton.title = label;
  els.pinChatButton.setAttribute("aria-label", label);
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
  const activityLabel =
    chat.status === "active"
      ? "updating live"
      : chat.status === "interrupted"
        ? `interrupted · ${formatRelativeTime(chatActivityAt(chat))}`
        : formatRelativeTime(chatActivityAt(chat));
  const meta = [
    chat.job_name || "one-shot",
    `${visibleMessageCount} message${visibleMessageCount === 1 ? "" : "s"}`,
    activityLabel,
  ].join(" · ");
  const metaFingerprint = JSON.stringify([title, meta, chat.status]);

  if (metaFingerprint === state.selectedMetaFingerprint) return;

  state.selectedMetaFingerprint = metaFingerprint;
  setConversationHeading(title, meta);
  const syncStatus =
    chat.status === "active" ? "active" : chat.status === "interrupted" ? "interrupted" : "cached";
  const syncLabel =
    chat.status === "active"
      ? "Syncing from SQLite"
      : chat.status === "interrupted"
        ? "Last run was interrupted"
        : "Cached in SQLite";
  setStatusIcon(els.syncLabel, syncStatus, syncLabel, "sync");
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
  els.viewport.classList.add("chat-switching");
  els.viewport.setAttribute("aria-busy", "true");
}

function cancelChatSwitch() {
  state.chatSwitchToken += 1;
  els.viewport.classList.remove("chat-switching");
  els.viewport.removeAttribute("aria-busy");
}

function finishChatSwitch(conversationId) {
  if (!els.viewport.classList.contains("chat-switching")) return;

  const token = state.chatSwitchToken;
  requestAnimationFrame(() => {
    if (token !== state.chatSwitchToken || state.selectedId !== conversationId) return;

    void getComputedStyle(els.conversation).opacity;
    els.viewport.classList.remove("chat-switching");
    els.viewport.removeAttribute("aria-busy");
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
    conversationRenderer.renderMessageNodes(visibleMessages, allowStreaming);
    state.renderedConversationId = chat.id;
    conversationRenderer.restoreConversationViewport(
      viewportSnapshot,
      isInitial && !rememberedViewport,
    );
  }

  finishChatSwitch(chat.id);
  renderConversationMeta(chat, visibleMessages.length);
  setHiddenIfChanged(els.emptyState, true);
  setHiddenIfChanged(els.conversation, false);
  els.messageInput.disabled = false;
  state.composingNew = false;
  syncComposerDraftTarget();
  syncSendButton();
  els.shareChatButton.disabled = false;
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
      ),
    )
    .find(Boolean);

  if (pendingActivity) {
    setTextIfChanged(els.composerStatus, pendingActivity.statusText);
  } else if (!state.sending) {
    setTextIfChanged(
      els.composerStatus,
      chat.status === "active"
        ? "Uses the existing live ChatGPT tab."
        : chat.status === "interrupted"
          ? "The last run was interrupted. Sending will reopen this chat."
          : "Sending will reopen this chat once if its retained tab has expired.",
    );
  }
}

function showMode(mode) {
  state.mode = mode === "logs" ? "logs" : "chats";
  const logsMode = state.mode === "logs";
  els.viewport.hidden = logsMode;
  logsPanel.setVisible(logsMode);
  els.composerFooter.hidden = logsMode;

  if (logsMode) {
    cancelChatSwitch();
    state.selectedMetaFingerprint = "";
    const display = displayServerName(state.serverName || location.hostname);
    setConversationHeading(`${display} Prompta logs`, `journalctl · prompta.service · ${display}`);
    setStatusIcon(els.syncLabel, "journal", `${display} journal`, "sync");
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    els.shareChatButton.disabled = true;
    setTextIfChanged(els.composerStatus, "Switch back to chats to send a message.");
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
  setHiddenIfChanged(els.emptyState, false);
  setHiddenIfChanged(els.conversation, true);
  conversationRenderer.renderMessageNodes([], false);
  setConversationHeading("Prompta", "Local conversation history");
  setStatusIcon(els.syncLabel, "local", "Local cache", "sync");
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  els.shareChatButton.disabled = true;
  updatePinButton();
  els.messageInput.placeholder = "Message Prompta…";
  setTextIfChanged(els.composerStatus, "");
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
      setHiddenIfChanged(els.emptyState, true);
      setHiddenIfChanged(els.conversation, false);
      conversationRenderer.renderMessageNodes(messages, true);
      conversationRenderer.restoreConversationViewport(viewportSnapshot, enteringNewChat);
    } else {
      setHiddenIfChanged(els.emptyState, false);
      setHiddenIfChanged(els.conversation, true);
      conversationRenderer.renderMessageNodes([], false);
    }

    setConversationHeading(
      "New chat",
      pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation",
    );
    setStatusIcon(
      els.syncLabel,
      pending ? "queued" : "new",
      pending ? "Send queued" : "Fresh conversation",
      "sync",
    );
    els.messageInput.disabled = false;
    syncSendButton();
    els.shareChatButton.disabled = true;
    updatePinButton();
    els.messageInput.placeholder = "Start a new chat…";
    const activity = pending
      ? pendingSendActivity(
          pending.status,
          Boolean(pending.sendId),
          pending.retryAfterSeconds,
          pending.retryAt,
          undefined,
          pending.queuePosition,
        )
      : null;
    setTextIfChanged(
      els.composerStatus,
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
    els.viewport.hidden = false;
    logsPanel.setVisible(false);
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    renderSidebar();
    scrollSidebarToNewest();
    sidebar.close();

    if (!waiting && matchMedia("(pointer: fine)").matches) {
      requestAnimationFrame(() => els.messageInput.focus());
    }
  }
}

async function fetchJson(url, timeoutMs = 10_000, controller = new AbortController()) {
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

    return await response.json();
  } finally {
    window.clearTimeout(timeout);
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
  let timeout: number | undefined;
  const cached = await Promise.race([
    Promise.all([recentChatCache.warm(), recentChatCache.warmSummaries()]),
    new Promise<null>((resolve) => {
      timeout = window.setTimeout(() => resolve(null), 500);
    }),
  ]);

  if (timeout !== undefined) window.clearTimeout(timeout);

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
  setTextIfChanged(
    els.cacheSummary,
    sidebarChatCountSummary(state.chats.length, activeCount, state.search),
  );
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
      setHiddenIfChanged(els.emptyState, true);
      setHiddenIfChanged(els.conversation, false);
    }
  }

  renderSidebar();

  return true;
}

async function loadServerIdentity() {
  try {
    const payload = await fetchJson("api/health");

    setServerStatus(payload.server, payload.online);
    const head = String(payload.head || "")
      .trim()
      .toLowerCase();
    deploymentMonitor.observeHead(head);
    setTextIfChanged(els.headLabel, head ? head : "unknown");
    els.headLabel.title = head ? "UI commit " + head : "UI commit unavailable";
  } catch (error) {
    setServerStatus(state.serverName || location.hostname, false);
    console.warn("Could not load Prompta server identity", error);
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

async function loadChats(forceSelectedRefresh = false) {
  const requestId = ++state.chatsRequestId;
  chatsRequestController?.abort();
  const requestController = new AbortController();
  chatsRequestController = requestController;

  try {
    const payload = await fetchJson(
      chatListRequestUrl(state.search, state.pinnedIds),
      10_000,
      requestController,
    );

    if (requestId !== state.chatsRequestId) return;

    const chats = payload.chats || [];
    promoteServerPendingPins(chats);
    reconcileOptimisticNew(chats);
    const orderedChats = sortSidebarChats(chats, state.pinnedIds);

    if (!state.search) recentChatCache.rememberSummaries(orderedChats);

    completionNotifications.trackCompletions(chats);
    state.chats = orderedChats;
    state.chatOrderScope = state.search;
    const activeCount = state.chats.filter((chat) => chat.status === "active").length;

    setTextIfChanged(
      els.cacheSummary,
      sidebarChatCountSummary(state.chats.length, activeCount, state.search),
    );
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
    } else {
      await logsPanel.load();
    }
  } catch (error) {
    if (requestId !== state.chatsRequestId) return;

    if (els.globalLiveOrb.classList.contains("live")) {
      els.globalLiveOrb.classList.remove("live");
    }

    setTextIfChanged(els.cacheSummary, "Cache unavailable");
    console.error(error);
  } finally {
    if (chatsRequestController === requestController) chatsRequestController = null;
  }
}

const HISTORICAL_ACTIVITY_PROBE_TTL_MS = 30_000;

async function probeHistoricalActivity(conversationId) {
  if (!conversationId || !shouldProbeHistoricalActivity(state.selectedChat?.status)) return;

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
    setTextIfChanged(els.composerStatus, "Checking whether ChatGPT is still running…");
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
      setTextIfChanged(
        els.composerStatus,
        "Could not verify whether this interrupted chat is still running.",
      );
    }

    console.warn("Could not probe historical chat activity", error);
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
    setHiddenIfChanged(els.emptyState, true);
    setHiddenIfChanged(els.conversation, false);
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
    const chat = await fetchJson(`api/chats/${encodeURIComponent(selectedId)}`, 30_000);

    if (
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
  els.messageInput.placeholder = "Message Prompta…";
  state.selectedId = id;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
  renderSidebar();
  await loadSelectedChat();
}

let searchTimer;

els.searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = els.searchInput.value.trim();
    state.sidebarFingerprint = "";
    void loadChats();
  }, 140);
});

document.addEventListener("keydown", (event) => {
  const searchFocused = document.activeElement === els.searchInput;
  const typing = searchFocused || document.activeElement === els.messageInput;

  if (event.key === "/" && !typing) {
    event.preventDefault();
    sidebar.open();
    els.searchInput.focus({ preventScroll: true });
  }

  if (event.key === "Escape") {
    if (searchFocused && els.searchInput.value) {
      event.preventDefault();
      clearTimeout(searchTimer);
      els.searchInput.value = "";
      state.search = "";
      state.sidebarFingerprint = "";
      void loadChats();

      return;
    }

    attachmentPicker.closeMenu();
    closeSlashMenu();
    jobsDialog.close();
    els.searchInput.blur();
    sidebar.close(true);
  }
});

els.newChatButton.addEventListener("click", () => {
  state.pendingNewSend = null;
  state.newChatFingerprint = "";
  renderNewChat();
});

function resizeComposer() {
  els.messageInput.style.overflowY = "hidden";

  if (!els.messageInput.value) {
    els.messageInput.style.height = "34px";

    return;
  }

  els.messageInput.style.height = "auto";
  const contentHeight = els.messageInput.scrollHeight;
  els.messageInput.style.height = `${Math.min(180, contentHeight)}px`;
  els.messageInput.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
}

async function runScheduleSlashCommand(command, originalMessage) {
  state.sending = true;
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();
  updateComposerActionButton();
  setTextIfChanged(els.composerStatus, "Saving schedule…");

  try {
    const result = await postJson("api/schedule", {
      interval_minutes: command.intervalMinutes,
      prompt: command.prompt,
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    const interval = formatScheduleInterval(Number(result.interval_minutes));
    const prefix = result.created === false ? "Already scheduled" : "Scheduled";
    setTextIfChanged(
      els.composerStatus,
      `${prefix} on ${server}: every ${interval} · ${command.prompt}`,
    );
  } catch (error) {
    els.messageInput.value = originalMessage;
    persistComposerDraft();
    resizeComposer();
    updateSlashMenu();
    setTextIfChanged(
      els.composerStatus,
      `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`,
    );
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();

    if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
  }
}

async function runAtSlashCommand(command, originalMessage) {
  state.sending = true;
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();
  updateSlashMenu();
  setTextIfChanged(els.composerStatus, "Saving one-time schedule…");

  try {
    const result = await postJson("api/schedule-at", {
      run_at_epoch: command.runAtEpoch,
      prompt: command.prompt,
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    setTextIfChanged(
      els.composerStatus,
      `Scheduled on ${server}: ${command.runAtLabel} · ${command.prompt}`,
    );
  } catch (error) {
    els.messageInput.value = originalMessage;
    persistComposerDraft();
    resizeComposer();
    updateSlashMenu();
    setTextIfChanged(
      els.composerStatus,
      `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`,
    );
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();

    if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
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
    ]) !== previous;

  if (changed) item.updatedAt = Date.now() / 1000;

  return changed;
}

function setPendingDeleteBusy(deleteKey: string, busy: boolean) {
  for (const button of els.conversation.querySelectorAll<HTMLButtonElement>(
    ".delete-pending-button",
  )) {
    if (button.dataset.deletePendingKey !== deleteKey) continue;

    button.disabled = busy;
    button.toggleAttribute("aria-busy", busy);
    button.closest(".message")?.classList.toggle("pending-message-deleting", busy);
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

  if (!sendId) {
    setTextIfChanged(
      els.composerStatus,
      "Message is still entering the queue. Try deleting again.",
    );

    return;
  }

  setPendingDeleteBusy(deleteKey, true);

  try {
    await deleteRequest("api/sends/" + encodeURIComponent(sendId));
  } catch (error) {
    setPendingDeleteBusy(deleteKey, false);
    console.warn("Could not delete pending Prompta send", error);
    setTextIfChanged(els.composerStatus, "Could not delete the pending message.");

    return;
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
    setTextIfChanged(els.composerStatus, "Message is still entering the queue. Try editing again.");

    return;
  }

  try {
    await deleteRequest("api/sends/" + encodeURIComponent(sendId));
  } catch (error) {
    console.warn("Could not cancel pending Prompta send for editing", error);
    setTextIfChanged(els.composerStatus, "Could not edit the pending message.");

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

  els.messageInput.value = pending.message || "";
  persistComposerDraft();
  resizeComposer();
  updateSlashMenu();
  syncSendButton();
  renderSidebar();

  const attachmentNames = (pending as UiPendingSend).attachmentNames || [];

  if (attachmentNames.length) {
    setTextIfChanged(
      els.composerStatus,
      "Editing pending message. Reattach the files before sending.",
    );
  } else {
    setTextIfChanged(els.composerStatus, "Editing pending message.");
  }

  els.messageInput.focus();
  els.messageInput.setSelectionRange(els.messageInput.value.length, els.messageInput.value.length);
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

        setTextIfChanged(
          els.composerStatus,
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

      if (nextConversationId) {
        completionNotifications.markActive(nextConversationId);
        promotePendingConversationPin(pendingNewSend, nextConversationId);
      }

      const changed =
        pendingNewSend.status !== status ||
        pendingNewSend.error !== nextError ||
        pendingNewSend.conversationId !== nextConversationId ||
        pendingNewSend.retryAfterSeconds !== nextRetryAfterSeconds ||
        pendingNewSend.retryAt !== nextRetryAt ||
        pendingNewSend.retryAttempt !== nextRetryAttempt ||
        pendingNewSend.queuePosition !== nextQueuePosition;
      Object.assign(pendingNewSend, {
        status,
        error: nextError,
        conversationId: nextConversationId,
        retryAfterSeconds: nextRetryAfterSeconds,
        retryAt: nextRetryAt,
        retryAttempt: nextRetryAttempt,
        queuePosition: nextQueuePosition,
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
        els.messageInput.placeholder = "Message Prompta…";
        setTextIfChanged(els.composerStatus, "Sent. Waiting for the cached response…");
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
    });

    if (changed) renderSidebar();

    if (state.selectedId === conversationId) await loadSelectedChat();

    if (status === "succeeded") {
      setTextIfChanged(els.composerStatus, "Sent. Waiting for the cached response…");
      await loadChats();

      return;
    }

    if (["failed", "dead_lettered"].includes(status)) {
      setTextIfChanged(
        els.composerStatus,
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

  els.messageInput.value = pending.message || "";
  resizeComposer();
  syncSendButton();

  if (((pending as UiPendingSend).attachmentNames || []).length) {
    setTextIfChanged(els.composerStatus, "Reattach the files, then send again.");
    els.messageInput.focus();

    return;
  }

  await sendSelectedMessage();
}

async function stopSelectedChat() {
  const conversationId = state.selectedId;

  if (!conversationId || state.mode !== "chats" || state.stopping) return;

  state.stopping = true;
  syncSendButton();
  setTextIfChanged(els.composerStatus, "Stopping response…");

  try {
    await postJson("api/chats/" + encodeURIComponent(conversationId) + "/stop", {});
    setTextIfChanged(els.composerStatus, "Stopped.");
    state.selectedFingerprint = "";
    state.selectedUpdatedAt = null;
    await loadSelectedChat();
    await loadChats();
  } catch (error) {
    setTextIfChanged(els.composerStatus, "Stop failed: " + String(error).replace(/^Error:\s*/, ""));
    console.error(error);
  } finally {
    state.stopping = false;
    syncSendButton();
  }
}

async function sendSelectedMessage() {
  const message = els.messageInput.value.trim();
  const creatingNew = state.composingNew;
  const conversationId = state.selectedId;
  const attachments = attachmentPicker.snapshot();

  if (!message || state.mode !== "chats" || state.sending) return;

  if (message.toLowerCase() === "/logs") {
    clearComposerDraft();
    els.messageInput.value = "";
    closeSlashMenu();
    resizeComposer();
    showMode("logs");

    return;
  }

  if (["/list", "/jobs"].includes(message.toLowerCase())) {
    await jobsDialog.open(true);

    return;
  }

  void completionNotifications.requestPermissionFromGesture();
  const scheduleCommand = parseScheduleSlashCommand(message);

  if (scheduleCommand) {
    if (attachments.length) {
      setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");

      return;
    }

    if ("error" in scheduleCommand) {
      setTextIfChanged(els.composerStatus, scheduleCommand.error);

      return;
    }

    await runScheduleSlashCommand(scheduleCommand, message);

    return;
  }

  const atCommand = parseAtSlashCommand(message);

  if (atCommand) {
    if (attachments.length) {
      setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");

      return;
    }

    if ("error" in atCommand) {
      setTextIfChanged(els.composerStatus, atCommand.error);

      return;
    }

    await runAtSlashCommand(atCommand, message);

    return;
  }

  if (!creatingNew && !conversationId) return;

  let serializedAttachments: Array<{ name: string; type: string; data: string }> = [];

  if (attachments.length) {
    state.sending = true;
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    attachmentPicker.setDisabled(true);
    setTextIfChanged(els.composerStatus, "Preparing attachments…");

    try {
      serializedAttachments = await attachmentPicker.serialize();
    } catch (error) {
      state.sending = false;
      els.messageInput.disabled = false;
      attachmentPicker.setDisabled(false);
      syncSendButton();
      setTextIfChanged(
        els.composerStatus,
        "Attachment failed: " + String(error).replace(/^Error:\s*/, ""),
      );

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
  els.sendButton.disabled = true;
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();

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

    if (!creatingNew) completionNotifications.markActive(conversationId);

    pending.sendId = result.send_id;
    pending.status = result.status || "queued";
    pending.queuePosition = Number(result.queue_position || 0);
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
    pending.status = "failed";
    pending.error = String(error).replace(/^Error:\s*/, "");
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
      els.messageInput.disabled = false;
      syncSendButton();

      if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
    } else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
      els.messageInput.disabled = false;
      syncSendButton();

      if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
    }

    updateComposerActionButton();
  }
}

async function copySelectedChatUrl() {
  if (!state.selectedId) return;

  const url = new URL(location.href);
  url.hash = `/${encodeURIComponent(state.selectedId)}`;

  try {
    await navigator.clipboard.writeText(url.toString());
    setTextIfChanged(els.composerStatus, "Chat link copied.");
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = url.toString();
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    setTextIfChanged(
      els.composerStatus,
      copied ? "Chat link copied." : "Could not copy the chat link.",
    );
  }
}

let activeSlashCommand = "";

function visibleSlashCommandButtons() {
  return Array.from(
    els.slashMenu.querySelectorAll<HTMLButtonElement>("[data-slash-command]:not([hidden])"),
  );
}

function setSlashMenuSelection(button: HTMLButtonElement | null) {
  activeSlashCommand = button ? String(button.dataset.slashCommand || "") : "";

  for (const candidate of els.slashMenu.querySelectorAll<HTMLButtonElement>(
    "[data-slash-command]",
  )) {
    candidate.setAttribute("aria-selected", String(candidate === button));
  }

  if (button?.id) els.messageInput.setAttribute("aria-activedescendant", button.id);
  else els.messageInput.removeAttribute("aria-activedescendant");
}

function closeSlashMenu() {
  els.slashMenu.hidden = true;
  els.messageInput.setAttribute("aria-expanded", "false");
  setSlashMenuSelection(null);
}

function updateSlashMenu() {
  const value = els.messageInput.value;
  const firstToken = value.split(/\s/, 1)[0].toLowerCase();
  const candidates = Array.from(
    els.slashMenu.querySelectorAll<HTMLButtonElement>("[data-slash-command]"),
  );
  const show = value.startsWith("/") && !value.includes("\n") && !value.includes(" ");

  for (const button of candidates) {
    const command = String(button.dataset.slashCommand || "")
      .trim()
      .toLowerCase();
    button.hidden = !(show && command.startsWith(firstToken));
  }

  const visible = visibleSlashCommandButtons();

  if (!visible.length) {
    closeSlashMenu();

    return;
  }

  els.slashMenu.hidden = false;
  els.messageInput.setAttribute("aria-expanded", "true");
  const selected =
    visible.find((button) => String(button.dataset.slashCommand || "") === activeSlashCommand) ||
    visible[0];
  setSlashMenuSelection(selected);
}

function moveSlashMenuSelection(direction: number) {
  const visible = visibleSlashCommandButtons();

  if (!visible.length) return null;

  const currentIndex = visible.findIndex(
    (button) => String(button.dataset.slashCommand || "") === activeSlashCommand,
  );
  const nextIndex = nextSlashCommandIndex(visible.length, currentIndex, direction);
  const next = visible[nextIndex] || null;
  setSlashMenuSelection(next);

  return next;
}

function insertSlashCommand(command) {
  els.messageInput.value = command;
  closeSlashMenu();
  resizeComposer();
  syncSendButton();
  els.messageInput.focus();
  els.messageInput.setSelectionRange(command.length, command.length);
}

els.pinChatButton.addEventListener("click", toggleSelectedPin);

els.shareChatButton.addEventListener("click", copySelectedChatUrl);

els.slashMenu.addEventListener("pointermove", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-slash-command]");

  if (button && !button.hidden) setSlashMenuSelection(button);
});

els.slashMenu.addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-slash-command]");

  if (!button) return;

  insertSlashCommand(String(button.dataset.slashCommand || ""));
});

els.messageForm.addEventListener("submit", (event) => {
  event.preventDefault();

  if (els.sendButton.dataset.action === "stop") void stopSelectedChat();
  else void sendSelectedMessage();
});

els.messageInput.addEventListener("input", () => {
  persistComposerDraft();
  resizeComposer();
  updateSlashMenu();
  syncSendButton();
});

els.messageInput.addEventListener("keydown", (event) => {
  if (!els.slashMenu.hidden) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveSlashMenuSelection(event.key === "ArrowUp" ? -1 : 1);

      return;
    }

    if (event.key === "Tab" || (event.key === "Enter" && !event.isComposing)) {
      const selected = visibleSlashCommandButtons().find(
        (button) => String(button.dataset.slashCommand || "") === activeSlashCommand,
      );

      if (selected) {
        event.preventDefault();
        insertSlashCommand(String(selected.dataset.slashCommand || ""));

        return;
      }
    }

    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeSlashMenu();

      return;
    }
  }

  const mobileInput =
    matchMedia("(max-width: 780px)").matches || matchMedia("(pointer: coarse)").matches;

  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput) {
    event.preventDefault();

    if (els.sendButton.dataset.action === "stop") void stopSelectedChat();
    else void sendSelectedMessage();
  }
});

window.addEventListener("hashchange", () => {
  const id = conversationIdFromHash(location.hash);

  if (id && id !== state.selectedId) void selectChat(id);
});

function refreshDisplayedTimes() {
  if (
    state.composingNew &&
    ["rate_limited", "retrying"].includes(state.pendingNewSend?.status || "")
  ) {
    state.newChatFingerprint = "";
    renderNewChat();
  } else if (
    state.selectedId &&
    (state.pendingReplies.get(state.selectedId) || []).some((item) =>
      ["rate_limited", "retrying"].includes(item.status || ""),
    )
  ) {
    state.selectedFingerprint = "";
    void loadSelectedChat();
  }

  renderSidebar();

  for (const time of els.chatList.querySelectorAll<HTMLElement>(".chat-time[data-activity-at]")) {
    setTextIfChanged(time, formatRelativeTime(Number(time.dataset.activityAt || 0)));
  }

  for (const time of els.conversation.querySelectorAll<HTMLElement>(
    ".message-timestamp[data-message-at]",
  )) {
    const age = time.querySelector<HTMLElement>(".message-age");

    if (!age) continue;

    const ageText = messageAgeText(Number(time.dataset.messageAt || 0));
    setTextIfChanged(age, ageText ? ` · ${ageText}` : "");
  }

  if (
    state.mode === "chats" &&
    state.selectedChat &&
    state.selectedChat.id === state.selectedId &&
    !state.composingNew
  ) {
    renderConversationMeta(state.selectedChat, state.selectedVisibleMessageCount);
  }
}

async function startApp() {
  deploymentMonitor.registerServiceWorker();
  void loadServerIdentity();
  await hydratePinnedIds();
  await hydratePendingSends();
  resizeComposer();
  const hydrated = await hydrateRecentChatCache();

  if (!hydrated) {
    conversationRenderer.renderLoadingState();
    setHiddenIfChanged(els.emptyState, true);
    setHiddenIfChanged(els.conversation, false);
  }

  document.documentElement.classList.remove("booting");
  // Cached detail gives us an instant first paint, but it is never authoritative
  // for a new app session. Server rendering/persistence semantics can change
  // without changing a conversation's updated_at, so fetch the selected detail
  // once before live updates take over.
  await loadChats(true);
  liveUpdates.start();
}

void startApp();
