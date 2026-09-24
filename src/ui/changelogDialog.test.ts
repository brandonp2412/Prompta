import { describe, expect, test } from "bun:test";

import { readFileSync } from "node:fs";

import { changelogEntries, changelogPage } from "./changelog";

const changelogDialogSource = readFileSync(
  new URL("./ChangelogDialog.svelte", import.meta.url),
  "utf8",
);

describe("changelog payload", () => {
  test("keeps commit titles and hashes for declarative rendering", () => {
    expect(changelogEntries({ changes: [{ title: "Fix jobs modal", hash: "abc1234" }] })).toEqual([
      { title: "Fix jobs modal", hash: "abc1234" },
    ]);
  });

  test("keeps pagination metadata for incremental rendering", () => {
    expect(
      changelogPage({
        changes: [{ title: "Newest", hash: "abc1234" }],
        has_more: true,
        total: 618,
      }),
    ).toEqual({
      changes: [{ title: "Newest", hash: "abc1234" }],
      hasMore: true,
      total: 618,
    });
  });

  test("rejects malformed payloads", () => {
    expect(changelogEntries({ changes: "not-an-array" })).toEqual([]);
    expect(changelogEntries(null)).toEqual([]);
    expect(changelogPage(null)).toEqual({ changes: [], hasMore: false, total: 0 });
  });

  test("announces loading and result status from the dialog", () => {
    expect(changelogDialogSource).toContain('aria-describedby="changelogDialogStatus"');
    expect(changelogDialogSource).toContain(
      '<p id="changelogDialogStatus" role="status" aria-live="polite" aria-atomic="true">{status}</p>',
    );
    expect(changelogDialogSource).toContain(
      'aria-busy={status.startsWith("Loading") || loadingMore}',
    );
  });
});
