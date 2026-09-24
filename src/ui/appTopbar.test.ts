import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("./App.svelte", import.meta.url), "utf8");

test("chat-only topbar actions stay out of Prompta and logs pages", () => {
  expect(appSource).toMatch(
    /\{#if appViewState\.mode === "chats"\}\s*<div class="topbar-actions" aria-label="Prompta actions">[\s\S]*?<\/div>\s*\{\/if\}/,
  );
  expect(appSource.match(/class="topbar-actions"/g)?.length).toBe(1);
});
