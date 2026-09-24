import type { SidebarFilterKey } from "./appViewState.svelte";

export const appActions = $state({
  onSearch: (_value: string) => {},
  onSidebarFilter: (_filter: SidebarFilterKey) => {},
  onClearSidebarFilters: () => {},
  onMarkAllRead: () => {},
  onNewChat: () => {},
  onPin: () => {},
  onShare: () => {},
  onPromptaPage: () => {},
  onPromptaPageClose: () => {},
  onUnattendedMode: () => {},
  onSubmit: () => {},
  onComposerInput: (_value: string) => {},
  onApplyUpdate: () => {},
  onHashChange: () => {},
  onPageHide: () => {},
  onPageShow: () => {},
});
