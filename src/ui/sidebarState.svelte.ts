let motionEnd = () => {};

export const sidebarState = $state({ open: false, moving: false, openerFocusRequest: 0 });

export type SidebarListModel = {
  emptyState: "none" | "search" | "filter" | "empty";
  hasMore: boolean;
  loadingMore: boolean;
  groups: Array<{
    label: string;
    chats: Array<{
      id: string;
      optimisticNew: boolean;
      statusClass: "active" | "complete" | "broken" | "neutral" | null;
      broken: boolean;
      statusLabel: string;
      title: string;
      preview: string;
      jobLabel: string;
      activityAt: string | number;
      pinned: boolean;
      unread: boolean;
    }>;
  }>;
};

export const sidebarListState = $state<{
  model: SidebarListModel;
  selectedConversationId: string;
}>({
  model: { emptyState: "none", hasMore: false, loadingMore: false, groups: [] },
  selectedConversationId: "",
});

export const sidebarListActions = $state<{
  onSelect: (chatId: string, optimisticNew: boolean) => void;
  onPin: (chatId: string) => void;
  onPrefetch: (chatId: string) => void;
  onLoadMore: () => void;
}>({
  onSelect: () => {},
  onPin: () => {},
  onPrefetch: () => {},
  onLoadMore: () => {},
});

export function configureSidebar(onMotionEnd: () => void) {
  motionEnd = onMotionEnd;
}

export function openSidebar() {
  sidebarState.moving = !sidebarState.open;
  sidebarState.open = true;
}

export function closeSidebar(restoreFocus = false) {
  const shouldRestoreFocus = restoreFocus && sidebarState.open;

  sidebarState.moving = sidebarState.open;
  sidebarState.open = false;

  if (shouldRestoreFocus) sidebarState.openerFocusRequest += 1;
}

export function finishSidebarMotion() {
  if (!sidebarState.moving) return;

  sidebarState.moving = false;
  motionEnd();
}
