import { describe, expect, test } from "bun:test";

import { popStackPage, pushStackPage, stackPageFromState } from "./stackNavigation";

describe("mobile stack navigation", () => {
  test("pushes a same-page browser-history entry for a stack page", () => {
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

    pushStackPage("jobs", historyApi, "https://example.test/#/chat");

    expect(stackPageFromState(state)).toBe("jobs");
    expect(state).toMatchObject({ existing: "value" });
    expect(pushedUrl).toBe("https://example.test/#/chat");
  });

  test("uses browser back only when the requested stack page is current", () => {
    let backs = 0;
    const historyApi = {
      back() {
        backs += 1;
      },
      state: { __promptaStackPage: "changelog" },
      pushState() {},
    };

    expect(popStackPage("jobs", historyApi)).toBeFalse();
    expect(popStackPage("changelog", historyApi)).toBeTrue();
    expect(backs).toBe(1);
  });

  test("ignores unrelated history state", () => {
    expect(stackPageFromState(null)).toBeNull();
    expect(stackPageFromState({ __promptaStackPage: "other" })).toBeNull();
  });
});
