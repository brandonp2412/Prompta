import type { ChatListStatus, RunSummary } from "./resultFormatting";

// A first-page refresh is authoritative when it covers every matching run.
// While older pages are loaded, retain only entries that still satisfy the
// status filter; never resurrect an old queued entry after it has completed.
export function reconcileResultPage(
  existing: RunSummary[],
  firstPage: RunSummary[],
  total: number,
  pageSize: number,
  status: ChatListStatus,
): RunSummary[] {
  const retained =
    total <= pageSize
      ? []
      : existing.filter(
          (item) =>
            !status ||
            (status === "needs_attention" ? item.needs_attention : item.status === status),
        );
  const byId = new Map([...retained, ...firstPage].map((item) => [item.send_id, item]));
  return [...byId.values()]
    .sort(
      (a, b) =>
        (b.updated_at || b.created_at) - (a.updated_at || a.created_at) ||
        b.created_at - a.created_at ||
        a.send_id.localeCompare(b.send_id),
    )
    .slice(0, Math.max(0, total));
}

// A shrinking result set can leave an empty page below the advertised total.
// Stop automatic scroll pagination instead of issuing the same GET indefinitely.
export function nextResultPageOffset(
  offset: number,
  receivedCount: number,
  total: number,
): number | null {
  if (receivedCount === 0 && offset < total) return null;
  return Math.min(total, offset + receivedCount);
}
