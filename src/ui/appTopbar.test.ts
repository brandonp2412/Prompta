import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("./App.svelte", import.meta.url), "utf8");

test("chat-only topbar actions stay out of Prompta and logs pages", () => {
  expect(appSource).toMatch(
    /\{#if appViewState\.mode === "chats"\}\s*<div class="topbar-actions" role="group" aria-label="Prompta actions">[\s\S]*?<\/div>\s*\{\/if\}/,
  );
  expect(appSource.match(/class="topbar-actions"/g)?.length).toBe(1);
});

test("server presence exposes its state beyond the visual orb", () => {
  expect(appSource).toMatch(
    /id="globalLiveOrb"[\s\S]*?role="img"[\s\S]*?aria-label=\{appViewState\.liveTitle\}/,
  );
});

test("brand navigation keeps its visible text as the accessible name", () => {
  const brandButton = appSource.match(
    /<button\s+type="button"\s+class=\{\["brand-home-button"[\s\S]*?<\/button>/,
  )?.[0];

  expect(brandButton).toBeDefined();
  expect(brandButton).not.toContain("aria-label=");
  expect(brandButton).toContain("<strong>Prompta</strong>");
  expect(brandButton).toContain('<span id="serverLabel">{serverLabel}</span>');
});

test("labeled action clusters expose group semantics", () => {
  expect(appSource).toContain(
    '<div class="sidebar-filters" role="group" aria-label="Conversation filters">',
  );
  expect(appSource).toContain(
    '<div class="topbar-actions" role="group" aria-label="Prompta actions">',
  );
});

test("version update notice keeps visible text in its accessible name", () => {
  expect(appSource).toContain('"Update available. Tap to update Prompta"');
  expect(appSource).toContain('"Updating Prompta…"');
  expect(appSource).toContain(
    '>{appViewState.updateApplying ? "Updating Prompta…" : "Update available"}</button>',
  );
});
