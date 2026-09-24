import { describe, expect, test } from "bun:test";
import type { RootContent } from "hast";
import type { Token, Tokens } from "marked";

import { injectToolCodeDiff, TOOL_CODE_DIFF_FIELD } from "./diffPreview";
import { codePresentation, highlightedCode, parseMarkdown, safeLinkHref } from "./markdown";

function codeToken(tokens: Token[]) {
  return tokens.find((token): token is Tokens.Code => token.type === "code");
}

function collectClasses(nodes: RootContent[], result: string[] = []) {
  for (const node of nodes) {
    if (node.type !== "element") continue;

    const classes = node.properties.className;

    if (Array.isArray(classes)) result.push(...classes.map(String));
    else if (typeof classes === "string") result.push(classes);

    collectClasses(node.children, result);
  }

  return result;
}

function collectText(nodes: RootContent[]) {
  let value = "";

  for (const node of nodes) {
    if (node.type === "text") value += node.value;
    else if (node.type === "element") value += collectText(node.children);
  }

  return value;
}

describe("tool-call markdown model", () => {
  test("extracts tool identity and timestamp without requiring expanded metadata", () => {
    const token = codeToken(
      parseMarkdown(
        [
          "~~~tool:files.search",
          JSON.stringify({
            created_at: 1_700_000_000,
            arguments: { search_query: [{ q: "rendering" }] },
            status: "completed",
          }),
          "~~~",
        ]
          .join("\n")
          .replaceAll("~~~", "```"),
      ),
    );

    expect(token).toBeDefined();
    const presentation = codePresentation(token!);

    expect(presentation?.tool?.name).toBe("files.search");
    expect(presentation?.tool?.time?.iso).toBe("2023-11-14T22:13:20.000Z");
    expect(presentation?.tool?.time?.text).toMatch(/^\d{1,2}:\d{2}:\d{2}(?:am|pm)$/);
    expect(presentation?.tool?.hasMeta).toBe(false);
  });

  test("keeps Serena control-plane calls compact", () => {
    const token = codeToken(
      parseMarkdown(
        [
          "~~~tool:Glass Serena · activate_project",
          JSON.stringify({ arguments: { project: "/home/example/project" }, status: "completed" }),
          "~~~",
        ]
          .join("\n")
          .replaceAll("~~~", "```"),
      ),
    );

    const presentation = codePresentation(token!);

    expect(presentation?.tool?.name).toBe("Glass Serena · activate_project");
    expect(presentation?.tool?.summary).toBe("");
    expect(presentation?.tool?.hasMeta).toBe(false);
  });

  test("extracts Python from execute_python and highlights it with Lowlight", () => {
    const token = codeToken(
      parseMarkdown(
        [
          "~~~tool:Glass · execute_python",
          JSON.stringify({ arguments: { code: "print(1)" }, status: "completed" }),
          "~~~",
        ]
          .join("\n")
          .replaceAll("~~~", "```"),
      ),
    );

    const presentation = codePresentation(token!);

    expect(presentation?.language).toBe("python");
    expect(presentation?.code).toBe("print(1)");
    expect(presentation?.highlight).toBe(true);
    expect(collectText(presentation?.highlighted || [])).toBe("print(1)");
    expect(
      collectClasses(presentation?.highlighted || []).some((name) => name.startsWith("hljs-")),
    ).toBe(true);
  });

  test("preserves reasoning summaries and tool identity parts", () => {
    const token = codeToken(
      parseMarkdown(
        [
          "~~~tool:Glass Serena · serena_repl",
          JSON.stringify({
            summary: "Remembering",
            arguments: { expression: "1 + 1" },
            status: "completed",
          }),
          "~~~",
        ]
          .join("\n")
          .replaceAll("~~~", "```"),
      ),
    );

    const presentation = codePresentation(token!);

    expect(presentation?.tool).toMatchObject({
      summary: "Remembering",
      action: "serena_repl",
      connector: "Glass Serena",
      hasMeta: true,
    });
  });

  test("extracts code diff metadata without leaking it into visible tool JSON", () => {
    const fence = String.fromCharCode(96, 96, 96);
    const block = [
      fence + "tool:Glass Serena · serena_repl",
      JSON.stringify({ summary: "Edit source", status: "completed" }, null, 2),
      fence,
    ].join("\n");
    const source = injectToolCodeDiff(block, {
      patch_text: "diff --git a/a.ts b/a.ts\n--- a/a.ts\n+++ b/a.ts\n@@ -1 +1 @@\n-old\n+new",
      changed_file_count: 1,
      additions: 1,
      deletions: 1,
      truncated: false,
    });
    const token = codeToken(parseMarkdown(source));
    const presentation = codePresentation(token!);

    expect(presentation?.tool?.diff).toMatchObject({
      changedFileCount: 1,
      additions: 1,
      deletions: 1,
      truncated: false,
    });
    expect(presentation?.code).not.toContain(TOOL_CODE_DIFF_FIELD);
    expect(JSON.parse(presentation?.code || "{}")).toEqual({
      summary: "Edit source",
      status: "completed",
    });
  });

  test("highlights unified diffs through the existing Lowlight path", () => {
    const nodes = highlightedCode("-old\n+new", "diff");

    expect(collectText(nodes)).toBe("-old\n+new");
    expect(collectClasses(nodes).some((name) => name === "hljs-deletion")).toBe(true);
    expect(collectClasses(nodes).some((name) => name === "hljs-addition")).toBe(true);
  });

  test("keeps structured tool payloads as plain AST text until expanded", () => {
    const token = codeToken(
      parseMarkdown(
        [
          "~~~tool:files.search",
          JSON.stringify({ arguments: { top_k: 5 }, result: "VERY_LARGE_TOOL_BODY" }),
          "~~~",
        ]
          .join("\n")
          .replaceAll("~~~", "```"),
      ),
    );

    const presentation = codePresentation(token!);

    expect(presentation?.language).toBe("json");
    expect(presentation?.highlight).toBe(false);
    expect(presentation?.highlighted).toEqual([{ type: "text", value: token!.text }]);

    const expanded = highlightedCode(presentation!.code, presentation!.language);
    expect(collectText(expanded)).toBe(token!.text);
    expect(collectClasses(expanded).some((name) => name.startsWith("hljs-"))).toBe(true);
  });
});

describe("streaming markdown", () => {
  test("closes an unfinished tool fence only for a live stream", () => {
    const source = ["Before", "", "~~~tool:files.search", '{"arguments":{"top_k":']
      .join("\n")
      .replaceAll("~~~", "```");

    const streaming = parseMarkdown(source, { renderIncompleteFence: true });
    const settled = parseMarkdown(source);

    expect(codeToken(streaming)).toBeDefined();
    expect(codePresentation(codeToken(streaming)!)?.tool?.name).toBe("files.search");
    expect(codeToken(settled)).toBeUndefined();
  });

  test("closes an unfinished ordinary code fence while streaming", () => {
    const source = ["~~~python", "print(1)"].join("\n").replaceAll("~~~", "```");
    const token = codeToken(parseMarkdown(source, { renderIncompleteFence: true }));
    const presentation = codePresentation(token!);

    expect(presentation?.language).toBe("python");
    expect(collectText(presentation?.highlighted || [])).toBe("print(1)");
  });
});

describe("message markdown", () => {
  test("uses Marked for GFM block structure", () => {
    const tokens = parseMarkdown(
      [
        "# Heading",
        "",
        "- Parent",
        "  - Child",
        "  - [x] Done",
        "- Sibling",
        "",
        "1. First",
        "2. Second",
        "",
        "> Quoted **text**",
        "",
        "| Name | State |",
        "| --- | ---: |",
        "| tool | done |",
      ].join("\n"),
    );

    expect(tokens.some((token) => token.type === "heading")).toBe(true);
    expect(tokens.filter((token) => token.type === "list")).toHaveLength(2);
    expect(tokens.some((token) => token.type === "blockquote")).toBe(true);

    const table = tokens.find((token): token is Tokens.Table => token.type === "table");
    expect(table?.header).toHaveLength(2);
    expect(table?.align).toEqual([null, "right"]);
  });

  test("recognizes wide GFM tables by their AST column count", () => {
    const table = parseMarkdown(
      ["| Name | State | Owner |", "| --- | --- | --- |", "| tool | done | prompta |"].join("\n"),
    ).find((token): token is Tokens.Table => token.type === "table");

    expect(table?.header).toHaveLength(3);
  });

  test("highlights ordinary Python and Dart through Lowlight/highlight.js", () => {
    const python = codePresentation(
      codeToken(
        parseMarkdown(
          ["~~~python", "def greet(name):", '    return f"Hello {name}"', "~~~"]
            .join("\n")
            .replaceAll("~~~", "```"),
        ),
      )!,
    );
    const dart = codePresentation(
      codeToken(
        parseMarkdown(["~~~dart", "final answer = 42;", "~~~"].join("\n").replaceAll("~~~", "```")),
      )!,
    );

    expect(collectClasses(python?.highlighted || []).some((name) => name.startsWith("hljs-"))).toBe(
      true,
    );
    expect(collectClasses(dart?.highlighted || []).some((name) => name.startsWith("hljs-"))).toBe(
      true,
    );
  });

  test("reuses settled markdown parse results without caching streaming snapshots", () => {
    const source = "Prompta markdown cache sentinel with **stable** content.";

    const first = parseMarkdown(source);
    const second = parseMarkdown(source);
    const streamingFirst = parseMarkdown(source, { renderIncompleteFence: true });
    const streamingSecond = parseMarkdown(source, { renderIncompleteFence: true });

    expect(second).toBe(first);
    expect(streamingSecond).not.toBe(streamingFirst);
  });

  test("reuses syntax highlighting for unchanged code", () => {
    const code = "const promptaCacheSentinel: number = 42;";
    const first = highlightedCode(code, "typescript");
    const second = highlightedCode(code, "typescript");

    expect(second).toBe(first);
    expect(collectText(second)).toBe(code);
  });

  test("allows only http(s) renderer links", () => {
    expect(safeLinkHref("https://example.com/path")).toBe("https://example.com/path");
    expect(safeLinkHref("javascript:alert(1)")).toBe("");
  });
});
