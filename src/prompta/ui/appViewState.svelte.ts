export type ComposerAction = "send" | "stop";
export type ViewMode = "chats" | "logs";

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
  chatSwitching: false,
  composerValue: "",
  composerPlaceholder: "Message Prompta…",
  composerDisabled: true,
  composerStatus: "",
  composerAction: "send" as ComposerAction,
  composerActionDisabled: true,
  shareDisabled: true,
  pinDisabled: true,
  pinActive: false,
  pinLabel: "Pin chat",
  updateAvailable: false,
  updateApplying: false,
  searchValue: "",
  activeSlashCommand: "",
  clockTick: Date.now(),
  bootComplete: false,
  composerFocusRequest: 0,
  composerSelectEndRequest: 0,
  searchFocusRequest: 0,
  sidebarTopRequest: 0,
});

export function requestComposerFocus(selectEnd = false) {
  appViewState.composerFocusRequest += 1;

  if (selectEnd) appViewState.composerSelectEndRequest += 1;
}

export function requestSearchFocus() {
  appViewState.searchFocusRequest += 1;
}

export function requestSidebarTop() {
  appViewState.sidebarTopRequest += 1;
}
