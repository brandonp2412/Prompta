// A bounded, process-local fallback when browser storage is blocked or stale.
// No draft contents are transmitted or written to a second storage system.
const drafts = new Map<string, string>();
// Keep only opaque upload receipts in tab memory, never the image bytes.
// Navigating away from the composer must not discard selected attachments.
export type ComposerImageRef = { ref: string; name: string; url: string };
const images = new Map<string, ComposerImageRef[]>();

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

export function readComposerImages(key: string): ComposerImageRef[] {
  return [...(images.get(key) || [])];
}

export function rememberComposerImages(key: string, value: ComposerImageRef[]): void {
  if (!key) return;
  images.delete(key);
  if (value.length) images.set(key, value.slice(0, 4));
  if (images.size > 48) {
    const oldest = images.keys().next().value;
    if (oldest) images.delete(oldest);
  }
}

export function clearComposerImages(key: string): void {
  images.delete(key);
}
