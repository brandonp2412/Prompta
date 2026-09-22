import { describe, expect, test } from "bun:test";

import { renderMarkdown } from "./markdown";

describe("tool-call rendering", () => {
  test("shows a tool call timestamp even without a reasoning summary", () => {
    const rendered = renderMarkdown([
      "```tool:files.search",
      JSON.stringify({
        created_at: 1_700_000_000,
        arguments: { search_query: [{ q: "rendering" }] },
        status: "completed",
      }),
      "```",
    ].join("\n"));

    expect(rendered).toContain("tool-has-meta");
    expect(rendered).toContain('class="tool-expanded-meta"');
    expect(rendered).toContain('class="tool-time"');
    expect(rendered).toContain('datetime="2023-11-14T22:13:20.000Z"');
    expect(rendered).toMatch(/class="tool-time"[^>]*>\d{1,2}:\d{2}:\d{2}(?:am|pm)<\/time>/);
    const summary = rendered.split('<summary class="code-header">')[1]?.split("</summary>")[0] || "";
    expect(summary).toContain('<span class="tool-primary-name">files.search</span>');
    expect(summary).not.toContain("<button");
    const expandedHeader = rendered.split("</summary>")[1]?.split("<pre>")[0] || "";
    expect(expandedHeader).toContain('<span class="tool-expanded-action">files.search</span>');
    expect(expandedHeader).not.toContain("code-language");
    expect(expandedHeader).not.toContain("tool-time");
    expect(expandedHeader).not.toContain("copy-code");
  });

  test("shows persisted reasoning titles in the collapsed tool row", () => {
    const rendered = renderMarkdown([
      "```tool:Glass Serena · serena_repl",
      JSON.stringify({
        summary: "Remembering",
        arguments: { expression: "1 + 1" },
        status: "completed",
      }),
      "```",
    ].join("\n"));

    const summary = rendered.split('<summary class="code-header">')[1]?.split("</summary>")[0] || "";
    expect(summary).toContain('<span class="tool-summary">Remembering</span>');
    expect(summary).not.toContain("Glass Serena · serena_repl");
    expect(summary).not.toContain(">tool call<");
    expect(rendered.match(/<span class="tool-summary">Remembering<\/span>/g)).toHaveLength(1);
    const expandedHeader = rendered.split("</summary>")[1]?.split("<pre>")[0] || "";
    expect(expandedHeader).toContain('<span class="tool-expanded-action">serena_repl</span>');
    expect(expandedHeader).toContain('<span class="tool-expanded-separator">|</span>');
    expect(expandedHeader).toContain('<span class="tool-expanded-connector">Glass Serena</span>');
    expect(expandedHeader.indexOf("serena_repl")).toBeLessThan(expandedHeader.indexOf("Glass Serena"));
  });

  test("syntax-highlights structured tool payloads", () => {
    const rendered = renderMarkdown([
      "```tool:files.search",
      JSON.stringify({
        arguments: { top_k: 5 },
        status: "completed",
      }, null, 2),
      "```",
    ].join("\n"));

    expect(rendered).toContain('class="language-json"');
    expect(rendered).toContain('class="syntax-property"');
    expect(rendered).toContain('class="syntax-number"');
    expect(rendered).toContain('class="syntax-string"');
  });
});

describe("message markdown", () => {
  test("syntax-highlights ordinary fenced code", () => {
    const rendered = renderMarkdown([
      "```python",
      "def greet(name):",
      '    return f"Hello {name}"',
      "```",
    ].join("\n"));

    expect(rendered).toContain('class="language-python"');
    expect(rendered).toContain('<span class="syntax-keyword">def</span>');
    expect(rendered).toContain('<span class="syntax-function">greet</span>');
    expect(rendered).toContain('<span class="syntax-keyword">return</span>');
  });

  test("renders nested lists and common markdown blocks", () => {
    const rendered = renderMarkdown([
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
    ].join("\n"));

    expect(rendered).toContain("<h1>Heading</h1>");
    expect(rendered).toContain("<ul><li>Parent<ul><li>Child</li>");
    expect(rendered).toContain('class="task-item"');
    expect(rendered).toContain("<ol><li>First</li><li>Second</li></ol>");
    expect(rendered).toContain("<blockquote><p>Quoted <strong>text</strong></p></blockquote>");
    expect(rendered).toContain("<table><thead>");
    expect(rendered).toContain('class="table-scroll"');
    expect(rendered).not.toContain("table-scroll-wide");
    expect(rendered).toContain('style="text-align:right"');
  });

  test("marks tables with three or more columns as horizontally scrollable", () => {
    const rendered = renderMarkdown([
      "| Name | State | Owner |",
      "| --- | --- | --- |",
      "| tool | done | prompta |",
    ].join("\n"));

    expect(rendered).toContain('class="table-scroll table-scroll-wide"');
  });
});
