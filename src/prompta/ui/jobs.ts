export const JOB_PROMPT_PREVIEW_LIMIT = 220;

export function jobPromptIsExpandable(promptValue: unknown) {
  const prompt = typeof promptValue === "string" ? promptValue.trim() : "";

  return prompt.length > JOB_PROMPT_PREVIEW_LIMIT || prompt.includes("\n");
}
