import { describe, expect, test } from "bun:test";

import { renderChangelogEntry } from "./changelogDialog";

describe("changelog entry rendering", () => {
  test("shows the commit hash as a trailing suffix", () => {
    expect(renderChangelogEntry({ title: "Fix jobs modal", hash: "abc1234" })).toBe(
      '<li class="changelog-entry"><span class="changelog-entry-title">Fix jobs modal</span><span class="changelog-entry-hash">#abc1234</span></li>',
    );
  });

  test("escapes changelog titles and hashes", () => {
    const rendered = renderChangelogEntry({
      title: '<script>alert("x")</script>',
      hash: "abc<123",
    });

    expect(rendered).not.toContain("<script>");
    expect(rendered).toContain("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;");
    expect(rendered).toContain("#abc&lt;123");
  });

  test("omits the suffix when a hash is unavailable", () => {
    expect(renderChangelogEntry({ title: "Local change" })).toBe(
      '<li class="changelog-entry"><span class="changelog-entry-title">Local change</span></li>',
    );
  });
});
