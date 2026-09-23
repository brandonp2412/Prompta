let motionEnd = () => {};

export const sidebarState = $state({ open: false, moving: false });

export type SidebarListModel = {
  emptyState: "none" | "search" | "filter" | "empty";
  groups: Array<{
    label: string;
    chats: Array<{
      id: string;
      selected: boolean;
      optimisticNew: boolean;
      statusClass: "active" | "complete" | "broken" | "neutral" | null;
      broken: boolean;
      statusLabel: string;
      title: string;
      preview: string;
      jobLabel: string;
      activityAt: string | number;
      relativeTime: string;
      pinned: boolean;
      unread: boolean;
    }>;
  }>;
};

export const sidebarListState = $state<{ model: SidebarListModel }>({
  model: { emptyState: "none", groups: [] },
});

export const sidebarListActions = $state<{
  onSelect: (chatId: string, optimisticNew: boolean) => void;
  onPin: (chatId: string) => void;
}>({
  onSelect: () => {},
  onPin: () => {},
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
