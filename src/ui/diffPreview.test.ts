import { describe, expect, test } from "bun:test";

import {
  extractToolCodeDiff,
  injectToolCodeDiff,
  normalizeToolCodeDiff,
  toolCodeDiffSummary,
  TOOL_CODE_DIFF_FIELD,
  unifiedDiffPresentation,
} from "./diffPreview";

const patch = [
  "diff --git a/src/a.ts b/src/a.ts",
  "index 1111111..2222222 100644",
  "--- a/src/a.ts",
  "+++ b/src/a.ts",
  "@@ -1 +1 @@",
  "-const value = 1;",
  "+const value = 2;",
  "diff --git a/src/b.py b/src/b.py",
  "index 3333333..4444444 100644",
  "--- a/src/b.py",
  "+++ b/src/b.py",
  "@@ -2,2 +2,2 @@",
  "-old = True",
  "+old = False",
].join("\n");

describe("tool diff preview model", () => {
  test("normalizes API metadata and keeps summary counts independent of patch text", () => {
    const diff = normalizeToolCodeDiff({
      patch_text: patch,
      changed_file_count: 2,
      additions: 2,
      deletions: 2,
      truncated: true,
      repository_root: "/ignored",
    });

    expect(diff).toEqual({
      patchText: patch,
      changedFileCount: 2,
      additions: 2,
      deletions: 2,
      truncated: true,
    });
    expect(toolCodeDiffSummary(diff!)).toBe("2 files · +2 −2");
  });

  test("injects diff metadata into its tool block and strips it from visible tool JSON", () => {
    const fence = String.fromCharCode(96, 96, 96);
    const block = [
      fence + "tool:Glass Serena · serena_repl",
      JSON.stringify({ summary: "Edit source", status: "completed" }, null, 2),
      fence,
    ].join("\n");
    const injected = injectToolCodeDiff(block, {
      patch_text: patch,
      changed_file_count: 2,
      additions: 2,
      deletions: 2,
      truncated: false,
    });

    expect(injected).toContain(TOOL_CODE_DIFF_FIELD);

    const firstNewline = injected.indexOf("\n");
    const body = injected.slice(firstNewline + 1, injected.lastIndexOf("\n" + fence));
    const extracted = extractToolCodeDiff(body);

    expect(extracted.diff).toMatchObject({
      changedFileCount: 2,
      additions: 2,
      deletions: 2,
      truncated: false,
    });
    expect(extracted.code).not.toContain(TOOL_CODE_DIFF_FIELD);
    expect(JSON.parse(extracted.code)).toEqual({ summary: "Edit source", status: "completed" });
  });

  test("parses files and hunks for structured unified-diff rendering", () => {
    const diff = normalizeToolCodeDiff({
      patch_text: patch,
      changed_file_count: 2,
      additions: 2,
      deletions: 2,
      truncated: false,
    })!;
    const presentation = unifiedDiffPresentation(diff);

    expect(presentation.highlight).toBe(true);
    expect(presentation.files).toHaveLength(2);
    expect(presentation.files[0]).toMatchObject({
      path: "src/a.ts",
      hunks: [{ header: "@@ -1 +1 @@", body: "-const value = 1;\n+const value = 2;" }],
    });
    expect(presentation.files[0].metadata).toContain("--- a/src/a.ts");
    expect(presentation.files[1].path).toBe("src/b.py");
  });

  test("disables syntax highlighting for large patches while preserving preview structure", () => {
    const largePatch = [
      "diff --git a/generated.txt b/generated.txt",
      "--- a/generated.txt",
      "+++ b/generated.txt",
      "@@ -1 +1,9000 @@",
      ...Array.from({ length: 9000 }, (_, index) => "+" + index),
    ].join("\n");
    const diff = normalizeToolCodeDiff({
      patch_text: largePatch,
      changed_file_count: 1,
      additions: 9000,
      deletions: 0,
      truncated: true,
    })!;

    const presentation = unifiedDiffPresentation(diff);

    expect(presentation.highlight).toBe(false);
    expect(presentation.files).toHaveLength(1);
    expect(presentation.files[0].hunks).toHaveLength(1);
  });
});
