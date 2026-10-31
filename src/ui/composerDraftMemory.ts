// A bounded, process-local fallback when browser storage is blocked or stale.
// No draft contents are transmitted or written to a second storage system.
const drafts = new Map<string, string>();
// Every local edit advances a revision, even when the user retypes identical text.
// A late send acknowledgment must not discard that newer intent.
const editRevisions = new Map<string, number>();
function edited(key: string): void {
  editRevisions.set(key, (editRevisions.get(key) ?? 0) + 1);
}
export function composerEditRevision(key: string): number {
  return editRevisions.get(key) ?? 0;
}
// Keep only opaque upload receipts in tab memory, never the image bytes.
// Navigating away from the composer must not discard selected attachments.
export type ComposerImageRef = { ref: string; name: string; url: string };
const images = new Map<string, ComposerImageRef[]>();
const imageStoragePrefix = "prompta.composer-images.v1.";

function validImage(value: unknown): value is ComposerImageRef {
  if (!value || typeof value !== "object") return false;
  if (
    !("ref" in value) ||
    typeof value.ref !== "string" ||
    !/^[0-9a-f]{64}\/[A-Za-z0-9._-]{1,100}$/.test(value.ref)
  )
    return false;
  return (
    "name" in value &&
    value.name === value.ref.split("/")[1] &&
    "url" in value &&
    value.url === "./api/images/" + value.ref
  );
}

export function readComposerDraft(key: string): string | undefined {
  return key ? drafts.get(key) : undefined;
}

export function rememberComposerDraft(key: string, value: string): void {
  if (!key) return;
  edited(key);
  drafts.delete(key);
  drafts.set(key, value.slice(0, 32000));
  if (drafts.size > 48) {
    const oldest = drafts.keys().next().value;
    if (oldest) drafts.delete(oldest);
  }
}

export function clearComposerDraft(key: string): void {
  edited(key);
  drafts.delete(key);
}

export function readComposerImages(key: string): ComposerImageRef[] {
  if (!key) return [];
  const cached = images.get(key);
  if (cached) return [...cached];
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(imageStoragePrefix + key) || "null");
    if (!Array.isArray(value) || value.length > 4 || !value.every(validImage)) return [];
    images.set(key, value);
    return [...value];
  } catch {
    return [];
  }
}

export function rememberComposerImages(key: string, value: ComposerImageRef[]): void {
  if (!key) return;
  edited(key);
  images.delete(key);
  if (value.length) images.set(key, value.slice(0, 4));
  if (images.size > 48) {
    const oldest = images.keys().next().value;
    if (oldest) images.delete(oldest);
  }
  try {
    if (value.length)
      sessionStorage.setItem(imageStoragePrefix + key, JSON.stringify(value.slice(0, 4)));
    else sessionStorage.removeItem(imageStoragePrefix + key);
  } catch {
    // The in-memory upload refs remain usable in privacy-restricted tabs.
  }
}

export function clearComposerImages(key: string): void {
  edited(key);
  images.delete(key);
  try {
    sessionStorage.removeItem(imageStoragePrefix + key);
  } catch {
    // A denied storage write cannot resurrect cleared in-memory attachments.
  }
}
