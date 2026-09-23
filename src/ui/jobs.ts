export const JOB_PROMPT_PREVIEW_LIMIT = 220;
export const JOBS_PAGE_SIZE = 10;

export function jobPromptIsExpandable(promptValue: unknown) {
  const prompt = typeof promptValue === "string" ? promptValue.trim() : "";

  return prompt.length > JOB_PROMPT_PREVIEW_LIMIT || prompt.includes("\n");
}

export function paginateJobs<T>(
  jobs: readonly T[],
  requestedPage: number,
  pageSize = JOBS_PAGE_SIZE,
) {
  const normalizedPageSize = Math.max(1, Math.floor(pageSize));
  const pageCount = Math.max(1, Math.ceil(jobs.length / normalizedPageSize));
  const page = Math.min(pageCount, Math.max(1, Math.floor(requestedPage)));
  const start = (page - 1) * normalizedPageSize;

  return {
    items: jobs.slice(start, start + normalizedPageSize),
    page,
    pageCount,
  };
}
