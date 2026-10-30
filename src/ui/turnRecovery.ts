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
  if (stored === null && sameRun && previous.length) return previous;
  return [original];
}
