import { describe, expect, test } from "bun:test";

import { jobPromptIsExpandable } from "./jobs";

describe("scheduled job prompt presentation", () => {
  test("keeps short prompts directly visible", () => {
    expect(jobPromptIsExpandable("Check the deployment.")).toBeFalse();
  });

  test("collapses long prompts behind an accessible details control", () => {
    const prompt = `Run the full end-to-end workflow and verify each user-visible state. ${"Keep checking regressions. ".repeat(10)}`;
    expect(jobPromptIsExpandable(prompt)).toBeTrue();
  });

  test("expands multiline prompts", () => {
    expect(jobPromptIsExpandable("first line\nsecond line")).toBeTrue();
  });
});
