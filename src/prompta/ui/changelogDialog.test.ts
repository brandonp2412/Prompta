import { describe, expect, test } from "bun:test";

import { changelogEntries, changelogHasMore } from "./changelog";

describe("changelog payload", () => {
  test("keeps commit titles and hashes for declarative rendering", () => {
    expect(changelogEntries({ changes: [{ title: "Fix jobs modal", hash: "abc1234" }] })).toEqual([
      { title: "Fix jobs modal", hash: "abc1234" },
    ]);
  });

  test("rejects malformed payloads", () => {
    expect(changelogEntries({ changes: "not-an-array" })).toEqual([]);
    expect(changelogEntries(null)).toEqual([]);
  });

  test("reads pagination state from the changelog payload", () => {
    expect(changelogHasMore({ changes: [], has_more: true })).toBe(true);
    expect(changelogHasMore({ changes: [], has_more: false })).toBe(false);
    expect(changelogHasMore(null)).toBe(false);
  });
});
