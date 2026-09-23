export type ComposerAction = "send" | "stop";
export type ViewMode = "chats" | "logs";
export type SidebarFilterKey = "unread" | "active" | "broken";

export const appViewState = $state({
  serverDisplay: "",
  serverLabel: "Server · local",
  serverOnline: null as boolean | null,
  live: false,
  liveTitle: "Cache status",
  headingTitle: "Prompta",
  headingMeta: "Local conversation history",
  syncStatus: "local",
  syncLabel: "Local cache",
  cacheSummary: "Reading local cache",
  headLabel: "…",
  headTitle: "View changelog",
  mode: "chats" as ViewMode,
  emptyVisible: true,
  conversationVisible: false,
  conversationPinnedToBottom: true,
  chatSwitching: false,
  composerValue: "",
  composerPlaceholder: "Message Prompta…",
  composerDisabled: true,
  composerStatus: "",
  actionToast: "",
  composerAction: "send" as ComposerAction,
  composerActionDisabled: true,
  shareDisabled: true,
  pinDisabled: true,
  pinActive: false,
  pinLabel: "Pin chat",
  updateAvailable: false,
  updateApplying: false,
  searchValue: "",
  sidebarFilters: { unread: false, active: false, broken: false },
  activeSlashCommand: "",
  clockTick: Math.floor(Date.now() / 60_000) * 60_000,
  bootComplete: false,
  composerFocusRequest: 0,
  composerSelectEndRequest: 0,
  searchFocusRequest: 0,
  searchBlurRequest: 0,
  sidebarTopRequest: 0,
});

export function requestComposerFocus(selectEnd = false) {
  appViewState.composerFocusRequest += 1;

  if (selectEnd) appViewState.composerSelectEndRequest += 1;
}

export function requestSearchFocus() {
  appViewState.searchFocusRequest += 1;
}

export function requestSearchBlur() {
  appViewState.searchBlurRequest += 1;
}

export function requestSidebarTop() {
  appViewState.sidebarTopRequest += 1;
}
