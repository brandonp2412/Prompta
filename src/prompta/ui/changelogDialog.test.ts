import { describe, expect, test } from "bun:test";

import { changelogEntries } from "./changelog";

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
});
