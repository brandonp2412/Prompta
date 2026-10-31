import type { LocalTurn } from "./resultFormatting";

// A local turns outage must never replace a verified multi-turn transcript
// with the original single-turn fallback on a background refresh.
export function recoverVisibleTurns(
  stored: LocalTurn[] | null,
  previous: LocalTurn[],
  original: LocalTurn,
  sameRun: boolean,
): LocalTurn[] {
  if (stored?.length) return stored;
  if (stored === null && sameRun && previous.length) {
    const first = previous[0];
    // The primary detail endpoint can advance while the optional turns GET
    // is unavailable. Refresh that original turn without hiding saved replies.
    if (first.reply_id || original.updated_at < first.updated_at) return previous;
    if (first.status === "completed" && original.status !== "completed") return previous;
    const toolCalls = original.tool_calls?.length ? original.tool_calls : first.tool_calls;
    const merged: LocalTurn = {
      ...first,
      ...original,
      ...(toolCalls ? { tool_calls: toolCalls } : {}),
      assistant_text:
        original.assistant_text.length >= first.assistant_text.length
          ? original.assistant_text
          : first.assistant_text,
      status: original.status,
    };
    if (
      merged.updated_at === first.updated_at &&
      merged.status === first.status &&
      merged.assistant_text === first.assistant_text &&
      merged.tool_calls === first.tool_calls
    )
      return previous;
    return [merged, ...previous.slice(1)];
  }
  return [original];
}
