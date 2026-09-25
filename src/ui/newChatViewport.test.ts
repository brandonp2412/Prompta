import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("./app.ts", import.meta.url), "utf8");
const composerSource = readFileSync(new URL("./Composer.svelte", import.meta.url), "utf8");

test("a new chat cannot inherit a stale jump-to-latest state", () => {
  expect(composerSource).toContain(
    "appViewState.conversationVisible && !appViewState.conversationPinnedToBottom",
  );
  expect(appSource).toContain(
    "const enteringNewChat = !state.composingNew;\n  if (enteringNewChat) appViewState.conversationPinnedToBottom = true;",
  );
});
