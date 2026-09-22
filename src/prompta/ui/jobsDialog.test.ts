import { describe, expect, test } from "bun:test";

import { renderJobPrompt } from "./jobsDialog";

describe("scheduled job prompt rendering", () => {
  test("keeps short prompts directly visible", () => {
    expect(renderJobPrompt("Check the deployment.")).toBe(
      '<div class="job-row-prompt">Check the deployment.</div>',
    );
  });

  test("collapses long prompts behind an accessible details control", () => {
    const prompt = `Run the full end-to-end workflow and verify each user-visible state. ${"Keep checking regressions. ".repeat(10)}`;
    const rendered = renderJobPrompt(prompt);

    expect(rendered).toContain('<details class="job-prompt-details">');
    expect(rendered).toContain('<summary class="job-prompt-summary">');
    expect(rendered).toContain("Show full prompt");
    expect(rendered).toContain("Hide prompt");
    expect(rendered).toContain('aria-hidden="true"');
    expect(rendered.match(/Run the full end-to-end workflow/g)).toHaveLength(2);
  });

  test("escapes prompt markup in both preview and expanded content", () => {
    const prompt = `<script>alert("x")</script> ${"long prompt ".repeat(30)}`;
    const rendered = renderJobPrompt(prompt);

    expect(rendered).not.toContain("<script>");
    expect(rendered).toContain("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;");
  });
});
