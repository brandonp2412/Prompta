import { describe, expect, test } from "bun:test";

const appSource = await Bun.file(new URL("./App.svelte", import.meta.url)).text();
const appLogicSource = await Bun.file(new URL("./app.ts", import.meta.url)).text();
const sidebarSource = await Bun.file(new URL("./SidebarList.svelte", import.meta.url)).text();
const messagesSource = await Bun.file(
  new URL("./ConversationMessages.svelte", import.meta.url),
).text();

describe("queue and search controls", () => {
  test("replaces the slash shortcut with a clear button once search has text", () => {
    expect(appSource).toContain("{#if appViewState.searchValue}");
    expect(appSource).toContain('class="search-clear"');
    expect(appSource).toContain('type="text"');
    expect(appSource).toContain('role="searchbox"');
    expect(appSource).not.toContain('type="search"');
    expect(appSource).toContain('aria-label="Clear search"');
    expect(appSource).toContain('appViewState.searchValue = "";');
    expect(appSource).toContain('appActions.onSearch("");');
    expect(appSource).toContain("requestSearchFocus();");
    expect(appSource).toContain("<kbd>/</kbd>");
  });

  test("offers direct recovery actions for empty search and filter results", () => {
    expect(sidebarSource).toContain("No cached chats match your search.");
    expect(sidebarSource).toContain(">Clear search</button>");
    expect(sidebarSource).toContain('appActions.onSearch("");');
    expect(sidebarSource).toContain("appViewState.searchFocusRequest += 1;");
    expect(sidebarSource).toContain("No conversations match these filters.");
    expect(sidebarSource).toContain(">Clear filters</button>");
    expect(sidebarSource).toContain("appActions.onClearSidebarFilters();");
    expect(appLogicSource).toContain("appActions.onClearSidebarFilters = () => {");
    expect(appLogicSource).toContain("appViewState.sidebarFilters[filter] = false;");
  });

  test("retains queue ETA metadata from the initial enqueue response", () => {
    expect(appLogicSource).toContain("pending.queueEtaAt = Number(result.queue_eta_at || 0);");
    expect(appLogicSource).toContain(
      "coalescedReply.queueEtaAt = Number(result.queue_eta_at || 0);",
    );
  });

  test("exposes send-next controls for bumpable pending messages", () => {
    expect(messagesSource).toContain("message.pending_bump_key");
    expect(messagesSource).toContain('aria-label="Send queued message next"');
    expect(messagesSource).toContain("conversationState.onBump");
    expect(messagesSource).toContain(">Send next</button>");
  });
});
