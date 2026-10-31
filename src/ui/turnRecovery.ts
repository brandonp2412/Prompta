import type { LocalTurn } from "./resultFormatting";

function mergeConfirmedTurn(previous: LocalTurn, incoming: LocalTurn): LocalTurn {
  // A second local GET can be older than one already rendered. Keep verified
  // branch identity and the richest completed content across either snapshot.
  if (previous.message_id && incoming.message_id && previous.message_id !== incoming.message_id)
    return previous;
  const latest = incoming.updated_at >= previous.updated_at ? incoming : previous;
  const older = latest === incoming ? previous : incoming;
  const latestCalls = latest.tool_calls?.length ?? 0;
  const olderCalls = older.tool_calls?.length ?? 0;
  return {
    ...latest,
    assistant_text:
      latest.assistant_text.length >= older.assistant_text.length
        ? latest.assistant_text
        : older.assistant_text,
    ...(olderCalls > latestCalls ? { tool_calls: older.tool_calls } : {}),
    status:
      latest.status === "completed" || older.status !== "completed" ? latest.status : "completed",
  };
}

function mergeConfirmedTurns(stored: LocalTurn[], previous: LocalTurn[]): LocalTurn[] {
  const byId = new Map(stored.map((turn) => [turn.reply_id, turn]));
  const previousIds = new Set(previous.map((turn) => turn.reply_id));
  // Persisted replies are append-only. A shorter read must not remove a turn
  // already confirmed in this view; a later successful read can advance it.
  return [
    ...previous.map((turn) => {
      const incoming = byId.get(turn.reply_id);
      return incoming ? mergeConfirmedTurn(turn, incoming) : turn;
    }),
    ...stored.filter((turn) => !previousIds.has(turn.reply_id)),
  ];
}

// A local turns outage must never replace a verified multi-turn transcript
// with the original single-turn fallback on a background refresh.
export function recoverVisibleTurns(
  stored: LocalTurn[] | null,
  previous: LocalTurn[],
  original: LocalTurn,
  sameRun: boolean,
): LocalTurn[] {
  if (stored?.length)
    return sameRun && previous.length ? mergeConfirmedTurns(stored, previous) : stored;
  if (stored?.length === 0 && sameRun && previous.length > 1) return previous;
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
