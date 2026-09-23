export type ChangelogEntry = { title?: string; hash?: string };

export function changelogEntries(payload: unknown): ChangelogEntry[] {
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray((payload as { changes?: unknown }).changes)
  )
    return [];

  return (payload as { changes: ChangelogEntry[] }).changes;
}
