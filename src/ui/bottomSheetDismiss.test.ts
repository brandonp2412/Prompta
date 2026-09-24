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
    expect(sidebarSource).toContain("onclick={markAllReadFromActions}");
    expect(sidebarSource).toContain("<span>Read all</span>");
  });

  test("dismisses pending-message actions when the backdrop is tapped", () => {
    expect(messagesSource).toContain("if (event.target === event.currentTarget) closeActions();");
  });

  test("gives every bottom-sheet action a visible icon", () => {
    const iconAction =
      /<button[^>]*class="pending-message-action[^"]*"[^>]*>[\s\S]*?<svg viewBox="0 0 24 24"/g;

    expect(sidebarSource.match(iconAction)).toHaveLength(3);
    expect(messagesSource.match(iconAction)).toHaveLength(4);
  });
});
