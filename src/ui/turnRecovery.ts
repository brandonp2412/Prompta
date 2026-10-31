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
    ...(older.conversation_id && !latest.conversation_id
      ? { conversation_id: older.conversation_id }
      : {}),
    ...(older.parent_id && !latest.parent_id ? { parent_id: older.parent_id } : {}),
    ...(older.message_id && !latest.message_id ? { message_id: older.message_id } : {}),
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
  let confirmed: LocalTurn[];
  if (stored?.length) {
    confirmed = sameRun && previous.length ? mergeConfirmedTurns(stored, previous) : stored;
  } else if (sameRun && previous.length && (stored === null || previous.length > 1)) {
    confirmed = previous;
  } else {
    confirmed = [original];
  }

  // The local turns and detail requests are independent. A stale turns page
  // must not hide a newer completed original or erase its tool summaries.
  const first = confirmed[0];
  if (first.reply_id || (first.status === "completed" && original.status !== "completed"))
    return confirmed;
  const current = mergeConfirmedTurn(first, original);
  if (
    current.updated_at === first.updated_at &&
    current.status === first.status &&
    current.assistant_text === first.assistant_text &&
    current.tool_calls === first.tool_calls &&
    current.user_text === first.user_text &&
    current.message_id === first.message_id &&
    current.conversation_id === first.conversation_id
  )
    return confirmed;
  return [current, ...confirmed.slice(1)];
}
