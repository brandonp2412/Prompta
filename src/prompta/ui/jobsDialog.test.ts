import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { jobPromptIsExpandable, jobVisibilityGroup } from "./jobs";

const jobsDialogSource = readFileSync(new URL("./JobsDialog.svelte", import.meta.url), "utf8");

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

  test("groups scheduler states into Active, Done, and Broken filters", () => {
    expect(jobVisibilityGroup("pending")).toBe("active");
    expect(jobVisibilityGroup("paused")).toBe("active");
    expect(jobVisibilityGroup("healthy")).toBe("done");
    expect(jobVisibilityGroup("failing")).toBe("broken");
    expect(jobVisibilityGroup("rate-limited")).toBe("broken");
  });

  test("renders independently toggleable visibility chips", () => {
    expect(jobsDialogSource).toContain('label: "Active"');
    expect(jobsDialogSource).toContain('label: "Done"');
    expect(jobsDialogSource).toContain('label: "Broken"');
    expect(jobsDialogSource).toContain("aria-pressed={visibility[option.key]}");
    expect(jobsDialogSource).toContain("{#each visibleJobs as job (job.name)}");
  });

  test("keeps mobile Jobs navigation on the stack presentation", () => {
    expect(jobsDialogSource).toContain('presentation = mobile.current ? "stack" : "modal";');
    expect(jobsDialogSource).toContain("data-presentation={presentation}");
    expect(jobsDialogSource).toContain('() => presentation === "modal"');
  });
});
