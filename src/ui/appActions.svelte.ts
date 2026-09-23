import type { SidebarFilterKey } from "./appViewState.svelte";

export const appActions = $state({
  onSearch: (_value: string) => {},
  onSidebarFilter: (_filter: SidebarFilterKey) => {},
  onMarkAllRead: () => {},
  onNewChat: () => {},
  onPin: () => {},
  onShare: () => {},
  onSubmit: () => {},
  onComposerInput: (_value: string) => {},
  onApplyUpdate: () => {},
  onHashChange: () => {},
  onPageHide: () => {},
  onPageShow: () => {},
});
