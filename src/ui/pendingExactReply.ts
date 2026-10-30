// Preserve an exact-branch reply's idempotency key across a reload or lost HTTP
// acknowledgment. Only opaque IDs and a hash are stored, never reply text.
type PendingExactReply = {
  fingerprint: string;
  replyId: string;
  createdAt: number;
};

const storageKey = "prompta.pending-exact-replies.v1";
const maxRecords = 128;
const maxAgeMs = 90 * 24 * 60 * 60 * 1000;
let memoryRecords: PendingExactReply[] = [];
let memoryOnly = false;

function valid(record: unknown, now: number): record is PendingExactReply {
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
    record.createdAt <= now &&
    record.createdAt > now - maxAgeMs
  );
}

function records(): PendingExactReply[] {
  const now = Date.now();
  if (!memoryOnly) {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (Array.isArray(stored)) {
        return stored.filter((item) => valid(item, now)).slice(-maxRecords);
      }
    } catch {
      // An unavailable store cannot erase this tab's pending request.
    }
  }
  return memoryRecords.filter((item) => valid(item, now)).slice(-maxRecords);
}

function persist(items: PendingExactReply[]): void {
  memoryRecords = items.slice(-maxRecords);
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
