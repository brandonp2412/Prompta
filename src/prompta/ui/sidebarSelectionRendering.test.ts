import { describe, expect, test } from "bun:test";

const appSource = await Bun.file(new URL("./app.ts", import.meta.url)).text();
const sidebarSource = await Bun.file(new URL("./SidebarList.svelte", import.meta.url)).text();
const sidebarStateSource = await Bun.file(
  new URL("./sidebarState.svelte.ts", import.meta.url),
).text();

function functionSource(name: string, nextMarker: string) {
  const start = appSource.indexOf(`async function ${name}`);
  const end = appSource.indexOf(nextMarker, start);

  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);

  return appSource.slice(start, end);
}

describe("sidebar selection rendering", () => {
  test("keeps selection outside the per-row sidebar model", () => {
    expect(sidebarStateSource).toContain("selectedConversationId: string");
    expect(sidebarStateSource).not.toContain("selected: boolean");
    expect(sidebarSource).toContain(
      "selected: chat.id === sidebarListState.selectedConversationId",
    );
  });

  test("selecting a chat updates selection without rebuilding the sidebar model", () => {
    const selectChatSource = functionSource("selectChat", "\nlet searchTimer");

    expect(selectChatSource).toContain("syncSidebarSelection();");
    expect(selectChatSource).not.toContain("renderSidebar();");
  });
});
