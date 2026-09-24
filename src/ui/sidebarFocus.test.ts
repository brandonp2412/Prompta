import { describe, expect, test } from "bun:test";

const appSource = await Bun.file(new URL("./App.svelte", import.meta.url)).text();
const sidebarStateSource = await Bun.file(
  new URL("./sidebarState.svelte.ts", import.meta.url),
).text();

describe("mobile sidebar focus recovery", () => {
  test("restores focus to the opener when Escape closes an open sidebar", () => {
    expect(sidebarStateSource).toContain("openerFocusRequest: 0");
    expect(sidebarStateSource).toContain(
      "const shouldRestoreFocus = restoreFocus && sidebarState.open;",
    );
    expect(sidebarStateSource).toContain(
      "if (shouldRestoreFocus) sidebarState.openerFocusRequest += 1;",
    );
    expect(appSource).toContain("{@attach focusOnRequest(() => sidebarState.openerFocusRequest)}");
    expect(appSource).toContain("closeSidebar(true);");
  });
});
