import { describe, expect, test } from "bun:test";

const sidebarSource = await Bun.file(new URL("./SidebarList.svelte", import.meta.url)).text();
const messagesSource = await Bun.file(
  new URL("./ConversationMessages.svelte", import.meta.url),
).text();

describe("mobile bottom-sheet dismissal", () => {
  test("dismisses chat actions when the backdrop is tapped", () => {
    expect(sidebarSource).toContain("if (event.target === event.currentTarget) closeActions();");
  });

  test("dismisses pending-message actions when the backdrop is tapped", () => {
    expect(messagesSource).toContain("if (event.target === event.currentTarget) closeActions();");
  });
});
