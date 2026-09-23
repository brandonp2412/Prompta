import { describe, expect, test } from "bun:test";

const sidebarSource = await Bun.file(new URL("./SidebarList.svelte", import.meta.url)).text();

describe("mobile sidebar chat selection", () => {
  test("selects a coarse-pointer tap on pointerup before a synthesized click can be lost", () => {
    expect(sidebarSource).toContain(
      "function endLongPress(event: PointerEvent, chatId: string, optimisticNew: boolean)",
    );
    expect(sidebarSource).toContain("suppressSelectChatId = chatId;");
    expect(sidebarSource).toContain("sidebarListActions.onSelect(chatId, optimisticNew);");
    expect(sidebarSource).toContain(
      "onpointerup={(event) => endLongPress(event, chat.id, chat.optimisticNew)}",
    );
    expect(sidebarSource).toContain("onpointercancel={cancelLongPress}");
  });
});
