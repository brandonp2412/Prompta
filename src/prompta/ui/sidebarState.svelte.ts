let motionEnd = () => {};

export const sidebarState = $state({ open: false, moving: false });

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
  onLoadMore: () => void;
}>({
  onSelect: () => {},
  onPin: () => {},
  onLoadMore: () => {},
});

export function configureSidebar(onMotionEnd: () => void) {
  motionEnd = onMotionEnd;
}

export function openSidebar() {
  sidebarState.moving = !sidebarState.open;
  sidebarState.open = true;
}

export function closeSidebar(_restoreFocus = false) {
  sidebarState.moving = sidebarState.open;
  sidebarState.open = false;
}

export function finishSidebarMotion() {
  if (!sidebarState.moving) return;

  sidebarState.moving = false;
  motionEnd();
}
