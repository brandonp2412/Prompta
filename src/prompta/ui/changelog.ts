export type ChangelogEntry = { title?: string; hash?: string };

export type ChangelogPage = {
  changes: ChangelogEntry[];
  hasMore: boolean;
  total: number;
};

export function changelogPage(payload: unknown): ChangelogPage {
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray((payload as { changes?: unknown }).changes)
  ) {
    return { changes: [], hasMore: false, total: 0 };
  }

  const source = payload as { changes: ChangelogEntry[]; has_more?: unknown; total?: unknown };
  const total = Number(source.total);

  return {
    changes: source.changes,
    hasMore: Boolean(source.has_more),
    total: Number.isFinite(total)
      ? Math.max(source.changes.length, Math.floor(total))
      : source.changes.length,
  };
}

export function changelogEntries(payload: unknown): ChangelogEntry[] {
  return changelogPage(payload).changes;
}
