// Preserve exact-branch replies and early follow-ups across lost HTTP receipts.
// Only opaque IDs and hashes are stored, never private message text.
type PendingExactReply = {
  fingerprint: string;
  replyId: string;
  createdAt: number;
};

const storageKey = "prompta.pending-exact-replies.v1";
// Never silently evict an unacknowledged receipt: capacity must fail closed.
const maxRecords = 1024;
let memoryRecords: PendingExactReply[] = [];
let memoryOnly = false;

function valid(record: unknown): record is PendingExactReply {
  if (!record || typeof record !== "object") return false;
  return (
    "fingerprint" in record &&
    typeof record.fingerprint === "string" &&
    /^[a-f0-9]{64}$/.test(record.fingerprint) &&
    "replyId" in record &&
    typeof record.replyId === "string" &&
    /^[a-f0-9]{32}$/.test(record.replyId) &&
    "createdAt" in record &&
    typeof record.createdAt === "number" &&
    Number.isFinite(record.createdAt) &&
    record.createdAt >= 0
  );
}

function records(): PendingExactReply[] {
  if (memoryOnly) return memoryRecords;
  let raw: string | null;
  try {
    raw = localStorage.getItem(storageKey);
  } catch {
    // A denied read cannot erase IDs already created in this page.
    return memoryRecords;
  }
  if (raw === null) return [];
  let stored: unknown;
  try {
    stored = JSON.parse(raw);
  } catch {
    throw new Error("Unresolved reply receipts are unreadable; no new send was attempted.");
  }
  if (!Array.isArray(stored) || stored.length > maxRecords || !stored.every(valid)) {
    // Preserve every uncertain request ID, even if an old entry is damaged.
    throw new Error("Unresolved reply receipts are unreadable; no new send was attempted.");
  }
  return stored;
}

function persist(items: PendingExactReply[]): void {
  if (items.length > maxRecords) {
    throw new Error("Unresolved reply receipts are at capacity; no new send was attempted.");
  }
  memoryRecords = items;
  try {
    localStorage.setItem(storageKey, JSON.stringify(memoryRecords));
    memoryOnly = false;
  } catch {
    memoryOnly = true;
  }
}

export async function pendingExactReplyRequest(
  sendId: string,
  conversationId: string,
  parentId: string,
  text: string,
): Promise<{ replyId: string; fingerprint: string; reused: boolean }> {
  const bytes = new TextEncoder().encode(JSON.stringify([sendId, conversationId, parentId, text]));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const fingerprint = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  const saved = records();
  const previous = saved.find((entry) => entry.fingerprint === fingerprint);
  if (previous) return { replyId: previous.replyId, fingerprint, reused: true };
  const replyId = crypto.randomUUID().replaceAll("-", "");
  persist([...saved, { fingerprint, replyId, createdAt: Date.now() }]);
  return { replyId, fingerprint, reused: false };
}

export function acknowledgeExactReplyRequest(fingerprint: string, replyId: string): void {
  persist(
    records().filter((entry) => entry.fingerprint !== fingerprint || entry.replyId !== replyId),
  );
}

// Keep one receipt per queued message, not one slot per chat: several early
// follow-ups can be in flight simultaneously without losing their retry IDs.
export async function pendingQueuedFollowupRequest(
  sendId: string,
  text: string,
): Promise<{ replyId: string; fingerprint: string; reused: boolean }> {
  // Match the old single-slot hash to migrate an unresolved legacy receipt.
  const bytes = new TextEncoder().encode(JSON.stringify([sendId, text]));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const fingerprint = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  const saved = records();
  const previous = saved.find((entry) => entry.fingerprint === fingerprint);
  if (previous) return { replyId: previous.replyId, fingerprint, reused: true };

  let legacyId = "";
  try {
    const legacy: unknown = JSON.parse(
      localStorage.getItem("prompta.pending-followup.v1." + sendId) || "null",
    );
    if (
      legacy &&
      typeof legacy === "object" &&
      "replyId" in legacy &&
      typeof legacy.replyId === "string" &&
      /^[A-Za-z0-9_-]{16,200}$/.test(legacy.replyId) &&
      (("fingerprint" in legacy && legacy.fingerprint === fingerprint) ||
        ("text" in legacy && legacy.text === text))
    ) {
      legacyId = legacy.replyId;
    }
  } catch {
    // Unavailable legacy storage must not prevent a safe new receipt.
  }
  const replyId = legacyId || crypto.randomUUID().replaceAll("-", "");
  persist([...saved, { fingerprint, replyId, createdAt: Date.now() }]);
  return { replyId, fingerprint, reused: !!legacyId };
}

export function acknowledgeQueuedFollowupRequest(
  sendId: string,
  fingerprint: string,
  replyId: string,
): void {
  acknowledgeExactReplyRequest(fingerprint, replyId);
  try {
    const key = "prompta.pending-followup.v1." + sendId;
    const legacy: unknown = JSON.parse(localStorage.getItem(key) || "null");
    if (legacy && typeof legacy === "object" && "replyId" in legacy && legacy.replyId === replyId) {
      localStorage.removeItem(key);
    }
  } catch {
    // A confirmed server receipt survives even if legacy cleanup is blocked.
  }
}
