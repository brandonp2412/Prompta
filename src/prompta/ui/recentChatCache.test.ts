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
