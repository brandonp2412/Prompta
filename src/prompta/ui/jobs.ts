export const JOB_PROMPT_PREVIEW_LIMIT = 220;

export type JobVisibilityGroup = "active" | "done" | "broken";

export function jobVisibilityGroup(statusValue: unknown): JobVisibilityGroup {
  const status = typeof statusValue === "string" ? statusValue.trim().toLowerCase() : "";

  if (status === "failing" || status === "rate-limited") return "broken";

  if (status === "healthy") return "done";

  return "active";
}

export function jobPromptIsExpandable(promptValue: unknown) {
  const prompt = typeof promptValue === "string" ? promptValue.trim() : "";

  return prompt.length > JOB_PROMPT_PREVIEW_LIMIT || prompt.includes("\n");
}
