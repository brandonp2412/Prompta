import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { JOBS_PAGE_SIZE, jobPromptIsExpandable, paginateJobs } from "./jobs";

const jobsPageSource = readFileSync(new URL("./JobsPage.svelte", import.meta.url), "utf8");

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

  test("paginates jobs in fixed-size pages", () => {
    const jobs = Array.from({ length: JOBS_PAGE_SIZE + 2 }, (_, index) => index + 1);
    const firstPage = paginateJobs(jobs, 1);
    const secondPage = paginateJobs(jobs, 2);

    expect(firstPage.items).toEqual(jobs.slice(0, JOBS_PAGE_SIZE));
    expect(firstPage.pageCount).toBe(2);
    expect(secondPage.items).toEqual(jobs.slice(JOBS_PAGE_SIZE));
  });

  test("clamps pagination after jobs are removed", () => {
    const jobs = Array.from({ length: JOBS_PAGE_SIZE }, (_, index) => index + 1);
    const pagination = paginateJobs(jobs, 3);

    expect(pagination.page).toBe(1);
    expect(pagination.pageCount).toBe(1);
    expect(pagination.items).toEqual(jobs);
  });

  test("renders accessible pagination controls", () => {
    expect(jobsPageSource).toContain('aria-label="Scheduled jobs pages"');
    expect(jobsPageSource).toContain("Page {pagination.page} of {pagination.pageCount}");
    expect(jobsPageSource).toContain("{#each pagination.items as job (job.name)}");
  });

  test("renders jobs as an inline page", () => {
    expect(jobsPageSource).toContain('class="jobs-page"');
    expect(jobsPageSource).toContain('aria-labelledby="jobsPageTitle"');
    expect(jobsPageSource).not.toContain("<dialog");
  });

  test("confirms destructive single-job removal and locks row actions while saving", () => {
    expect(jobsPageSource).toContain("confirm(`Remove scheduled job “${job.name}”?`)");
    expect(jobsPageSource).toContain("onclick={() => void remove(job)}");
    expect(jobsPageSource.match(/class="job-action"\s+disabled=\{saving\}/g)?.length).toBe(3);
  });

  test("makes edit cancellation explicit", () => {
    expect(jobsPageSource).toContain('{editing ? "Cancel edit" : "Reset"}');
  });
});
