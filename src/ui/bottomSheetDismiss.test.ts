import { describe, expect, test } from "bun:test";

const appSource = await Bun.file(new URL("./App.svelte", import.meta.url)).text();
const sidebarSource = await Bun.file(new URL("./SidebarList.svelte", import.meta.url)).text();
const messagesSource = await Bun.file(
  new URL("./ConversationMessages.svelte", import.meta.url),
).text();

describe("mobile bottom-sheet dismissal", () => {
  test("dismisses chat actions when the backdrop is tapped", () => {
    expect(sidebarSource).toContain("if (event.target === event.currentTarget) closeActions();");
  });

  test("moves Read all from the sidebar toolbar into chat actions", () => {
    expect(appSource).not.toContain(">Read all</button>");
    expect(sidebarSource).toContain(
      '<button type="button" class="pending-message-action" onclick={markAllReadFromActions}>Read all</button>',
    );
  });

  test("dismisses pending-message actions when the backdrop is tapped", () => {
    expect(messagesSource).toContain("if (event.target === event.currentTarget) closeActions();");
  });
});
