// Remember only an opaque hash and queue request ID, never the prompt or attachments.
// A lost HTTP receipt must not turn a later explicit Send into a second fresh chat.
type PendingFreshRequest = {
  fingerprint: string;
  requestId: string;
  createdAt: number;
};

const storageKey = "prompta.pending-fresh-requests.v1";
const maxRecords = 128;
const maxAgeMs = 14 * 24 * 60 * 60 * 1000;
let memoryRecords: PendingFreshRequest[] = [];
// A browser can allow reads while rejecting writes (quota, policy or storage errors).
// Once that happens, local memory must win until a later write succeeds.
let memoryOnly = false;

function valid(record: unknown, now: number): record is PendingFreshRequest {
  if (!record || typeof record !== "object") return false;
  return (
    "fingerprint" in record &&
    typeof record.fingerprint === "string" &&
    /^[a-f0-9]{64}$/.test(record.fingerprint) &&
    "requestId" in record &&
    typeof record.requestId === "string" &&
    /^[a-f0-9]{32}$/.test(record.requestId) &&
    "createdAt" in record &&
    typeof record.createdAt === "number" &&
    Number.isFinite(record.createdAt) &&
    record.createdAt <= now &&
    record.createdAt > now - maxAgeMs
  );
}

function records(): PendingFreshRequest[] {
  const now = Date.now();
  if (!memoryOnly) {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (Array.isArray(stored)) {
        return stored.filter((item) => valid(item, now)).slice(-maxRecords);
      }
    } catch {
      // Storage may be unavailable or damaged. Keep same-page safety in memory.
    }
  }
  return memoryRecords.filter((item) => valid(item, now)).slice(-maxRecords);
}

function persist(items: PendingFreshRequest[]): void {
  memoryRecords = items.slice(-maxRecords);
  try {
    localStorage.setItem(storageKey, JSON.stringify(memoryRecords));
    memoryOnly = false;
  } catch {
    // A readable but unwritable store must not erase an unresolved request ID.
    memoryOnly = true;
  }
}

export async function freshQueueRequest(
  prompt: string,
  images: string[],
  scope = "chat",
): Promise<{ requestId: string; fingerprint: string; reused: boolean }> {
  const bytes = new TextEncoder().encode(JSON.stringify([scope, prompt.trim(), images]));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const fingerprint = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  const saved = records();
  const previous = saved.find((entry) => entry.fingerprint === fingerprint);
  if (previous) return { requestId: previous.requestId, fingerprint, reused: true };
  const requestId = crypto.randomUUID().replaceAll("-", "");
  persist([...saved, { fingerprint, requestId, createdAt: Date.now() }]);
  return { requestId, fingerprint, reused: false };
}

export async function findFreshQueueReceipt(requestId: string): Promise<string | null> {
  try {
    const response = await fetch("./api/chats/requests/" + requestId, { cache: "no-store" });
    if (!response.ok) return null;
    const body = (await response.json()) as { send_id?: string };
    return body.send_id === "manual-" + requestId ? body.send_id : null;
  } catch {
    return null;
  }
}

export function acknowledgeFreshQueueRequest(fingerprint: string, requestId: string): void {
  // Clearing one accepted receipt must not erase other unresolved submissions.
  persist(
    records().filter((entry) => entry.fingerprint !== fingerprint || entry.requestId !== requestId),
  );
}
