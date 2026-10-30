import type { ResultStatus, RunSummary } from "./resultFormatting";

// A first-page refresh is authoritative when it covers every matching run.
// While older pages are loaded, retain only entries that still satisfy the
// status filter; never resurrect an old queued entry after it has completed.
export function reconcileResultPage(
  existing: RunSummary[],
  firstPage: RunSummary[],
  total: number,
  pageSize: number,
  status: ResultStatus | "",
): RunSummary[] {
  const retained =
    total <= pageSize ? [] : existing.filter((item) => !status || item.status === status);
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
