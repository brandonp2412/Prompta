import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { popStackPage, pushStackPage, stackPageFromState } from "./stackNavigation";

const promptaPageSource = readFileSync(new URL("./PromptaPage.svelte", import.meta.url), "utf8");
const changelogDialogSource = readFileSync(
  new URL("./ChangelogDialog.svelte", import.meta.url),
  "utf8",
);

describe("Prompta stack navigation", () => {
  test("pushes a same-page browser-history entry for the Prompta page", () => {
    let state: unknown = { existing: "value" };
    let pushedUrl = "";
    const historyApi = {
      back() {},
      get state() {
        return state;
      },
      pushState(nextState: unknown, _unused: string, url?: string | URL | null) {
        state = nextState;
        pushedUrl = String(url || "");
      },
    };

    pushStackPage("prompta", historyApi, "https://example.test/#/chat");

    expect(stackPageFromState(state)).toBe("prompta");
    expect(state).toMatchObject({ existing: "value" });
    expect(pushedUrl).toBe("https://example.test/#/chat");
  });

  test("uses browser back only while the Prompta stack entry is current", () => {
    let backs = 0;
    const historyApi = {
      back() {
        backs += 1;
      },
      state: { __promptaStackPage: "prompta" },
      pushState() {},
    };

    expect(popStackPage("prompta", historyApi)).toBeTrue();
    expect(backs).toBe(1);

    historyApi.state = { __promptaStackPage: "other" };
    expect(popStackPage("prompta", historyApi)).toBeFalse();
    expect(backs).toBe(1);
  });

  test("recognizes every supported mobile stack page and ignores unrelated history state", () => {
    expect(stackPageFromState({ __promptaStackPage: "prompta" })).toBe("prompta");
    expect(stackPageFromState({ __promptaStackPage: "changelog" })).toBe("changelog");
    expect(stackPageFromState(null)).toBeNull();
    expect(stackPageFromState({ __promptaStackPage: "other" })).toBeNull();
  });

  test("renders the controls page as a mobile stack with an explicit back action", () => {
    expect(promptaPageSource).toContain("data-presentation={presentation}");
    expect(promptaPageSource).toContain('aria-label="Back to chats"');
    expect(promptaPageSource).toContain('pushStackPage("prompta")');
    expect(promptaPageSource).toContain("appActions.onPromptaPageClose()");
  });

  test("integrates the mobile changelog stack with browser back navigation", () => {
    expect(changelogDialogSource).toContain('pushStackPage("changelog")');
    expect(changelogDialogSource).toContain('popStackPage("changelog")');
    expect(changelogDialogSource).toContain(
      'aria-label={presentation === "stack" ? "Back to chats" : "Close changelog"}',
    );
    expect(changelogDialogSource).toContain("<svelte:window onpopstate={handlePopState} />");
  });
});
