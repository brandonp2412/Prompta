// A bounded, process-local fallback when browser storage is blocked or stale.
// No draft contents are transmitted or written to a second storage system.
const drafts = new Map<string, string>();

export function readComposerDraft(key: string): string | undefined {
  return key ? drafts.get(key) : undefined;
}

export function rememberComposerDraft(key: string, value: string): void {
  if (!key) return;
  drafts.delete(key);
  drafts.set(key, value.slice(0, 32000));
  if (drafts.size > 48) {
    const oldest = drafts.keys().next().value;
    if (oldest) drafts.delete(oldest);
  }
}

export function clearComposerDraft(key: string): void {
  drafts.delete(key);
}
