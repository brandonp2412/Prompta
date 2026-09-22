const PINNED_CHATS_KEY = "prompta:pinned-chats";

const COMPOSER_DRAFTS_KEY = "prompta:composer-drafts";

export function loadPinnedIds(): Set<string> {
  try {
    const stored = JSON.parse(localStorage.getItem(PINNED_CHATS_KEY) || "[]");
    return new Set(Array.isArray(stored) ? stored.map((id) => String(id)) : []);
  } catch {
    return new Set();
  }
}

export function savePinnedIds(pinnedIds: Set<string>) {
  try {
    localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(Array.from(pinnedIds)));
  } catch {}
}

export function loadComposerDrafts() {
  try {
    const stored = JSON.parse(localStorage.getItem(COMPOSER_DRAFTS_KEY) || "{}");
    if (!stored || Array.isArray(stored) || typeof stored !== "object") return new Map();
    return new Map(
      Object.entries(stored)
        .filter(([, value]) => typeof value === "string" && value)
        .map(([key, value]) => [key, typeof value === "string" ? value : ""]),
    );
  } catch {
    return new Map();
  }
}

export function saveComposerDrafts(composerDrafts: Map<string, string>) {
  try {
    localStorage.setItem(COMPOSER_DRAFTS_KEY, JSON.stringify(Object.fromEntries(composerDrafts)));
  } catch {}
}
