import { expect, test } from "bun:test";

import { RecentChatCache } from "./recentChatCache";

test("coalesces unchanged recent chat summary cache writes", () => {
  const cache = new RecentChatCache("/test");

  const initial = [
    { id: "first", title: "First", updated_at: 10 },
    { id: "second", title: "Second", updated_at: 8 },
  ];

  expect(cache.rememberSummaries(initial)).toBe(true);
  expect(cache.rememberSummaries(initial.map((chat) => ({ ...chat })))).toBe(false);

  const changed = initial.map((chat) =>
    chat.id === "first" ? { ...chat, updated_at: 11 } : { ...chat },
  );

  expect(cache.rememberSummaries(changed)).toBe(true);
  expect(cache.rememberSummaries(changed.map((chat) => ({ ...chat })))).toBe(false);
});

test("keeps recent chat state in memory without browser persistence", async () => {
  const cache = new RecentChatCache("/test", 2);
  const source = await Bun.file(import.meta.dir + "/recentChatCache.ts").text();

  expect(source).not.toContain("indexedDB");
  expect(source).not.toContain("IDBDatabase");

  cache.remember({ id: "first", title: "First" });
  cache.remember({ id: "second", title: "Second" });
  cache.remember({ id: "third", title: "Third" });

  expect(await cache.get("first")).toBeNull();
  expect(await cache.get("third")).toEqual({ id: "third", title: "Third" });

  cache.rememberSummaries([
    { id: "third", title: "Third" },
    { id: "second", title: "Second" },
  ]);
  expect(await cache.warmSummaries()).toEqual([
    { id: "third", title: "Third" },
    { id: "second", title: "Second" },
  ]);
});
