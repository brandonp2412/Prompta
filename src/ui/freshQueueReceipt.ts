import { localGet } from "./localRead";

// Remember only an opaque hash and queue request ID, never the prompt or attachments.
// A lost HTTP receipt must not turn a later explicit Send into a second fresh chat.
type PendingFreshRequest = {
  fingerprint: string;
  requestId: string;
  createdAt: number;
};

const storageKey = "prompta.pending-fresh-requests.v1";
// Never silently evict an unresolved fresh-chat request ID.
const maxRecords = 1024;
let memoryRecords: PendingFreshRequest[] = [];
// A browser can allow reads while rejecting writes (quota, policy or storage errors).
// Once that happens, local memory must win until a later write succeeds.
let memoryOnly = false;

function valid(record: unknown): record is PendingFreshRequest {
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
    record.createdAt >= 0
  );
}

function records(): PendingFreshRequest[] {
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
    throw new Error("Unresolved chat receipts are unreadable; no new send was attempted.");
  }
  if (!Array.isArray(stored) || stored.length > maxRecords || !stored.every(valid)) {
    // Never silently discard a damaged record: it could identify a real send.
    throw new Error("Unresolved chat receipts are unreadable; no new send was attempted.");
  }
  return stored;
}

function persist(items: PendingFreshRequest[]): void {
  if (items.length > maxRecords) {
    throw new Error("Unresolved chat requests are at capacity; no new send was attempted.");
  }
  memoryRecords = items;
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

export type FreshQueueReceipt = { sendId: string; status: string };

export async function findFreshQueueReceiptStatus(
  requestId: string,
): Promise<FreshQueueReceipt | null> {
  try {
    const response = await localGet("./api/chats/requests/" + requestId);
    if (!response.ok) return null;
    const body = (await response.json()) as { send_id?: string; status?: string };
    return body.send_id === "manual-" + requestId && typeof body.status === "string"
      ? { sendId: body.send_id, status: body.status }
      : null;
  } catch {
    return null;
  }
}

export async function findFreshQueueReceipt(requestId: string): Promise<string | null> {
  return (await findFreshQueueReceiptStatus(requestId))?.sendId ?? null;
}

export function acknowledgeFreshQueueRequest(fingerprint: string, requestId: string): void {
  // Clearing one accepted receipt must not erase other unresolved submissions.
  persist(
    records().filter((entry) => entry.fingerprint !== fingerprint || entry.requestId !== requestId),
  );
}
