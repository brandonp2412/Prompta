import { expect, test } from "bun:test";
import {
  acknowledgeQueuedFollowupRequest,
  pendingQueuedFollowupRequest,
} from "../src/ui/pendingExactReply";

function withStorage<T>(
  storage: { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void; removeItem?: (key: string) => void },
  action: () => Promise<T>,
): Promise<T> {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
  return action().finally(() => {
    if (previous) Object.defineProperty(globalThis, "localStorage", previous);
    else Reflect.deleteProperty(globalThis, "localStorage");
  });
}

test("multiple uncertain follow-ups retain independent IDs across reloads and acknowledgments", async () => {
  const stored = new Map<string, string>();
  await withStorage({
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => { stored.set(key, value); },
    removeItem: (key) => { stored.delete(key); },
  }, async () => {
    const sendId = "run-" + crypto.randomUUID();
    const firstText = "First private follow-up " + crypto.randomUUID();
    const secondText = "Second private follow-up " + crypto.randomUUID();
    const first = await pendingQueuedFollowupRequest(sendId, firstText);
    const second = await pendingQueuedFollowupRequest(sendId, secondText);
    expect(first.replyId).not.toBe(second.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, firstText)).replyId).toBe(first.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, secondText)).replyId).toBe(second.replyId);
    expect(JSON.stringify([...stored.values()])).not.toContain(firstText);
    expect(JSON.stringify([...stored.values()])).not.toContain(secondText);
    acknowledgeQueuedFollowupRequest(sendId, first.fingerprint, first.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, secondText)).replyId).toBe(second.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, firstText)).replyId).not.toBe(first.replyId);
  });
});

test("an unresolved legacy follow-up keeps its original ID during migration", async () => {
  const stored = new Map<string, string>();
  await withStorage({
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => { stored.set(key, value); },
    removeItem: (key) => { stored.delete(key); },
  }, async () => {
    const sendId = "legacy-" + crypto.randomUUID();
    const text = "Legacy pending follow-up " + crypto.randomUUID();
    const fingerprint = Array.from(new Uint8Array(await crypto.subtle.digest(
      "SHA-256", new TextEncoder().encode(JSON.stringify([sendId, text])),
    )), (byte) => byte.toString(16).padStart(2, "0")).join("");
    const replyId = crypto.randomUUID().replaceAll("-", "");
    const legacyKey = "prompta.pending-followup.v1." + sendId;
    stored.set(legacyKey, JSON.stringify({ replyId, fingerprint }));
    const migrated = await pendingQueuedFollowupRequest(sendId, text);
    expect(migrated.replyId).toBe(replyId);
    expect(migrated.reused).toBe(true);
    expect((await pendingQueuedFollowupRequest(sendId, text)).replyId).toBe(replyId);
    acknowledgeQueuedFollowupRequest(sendId, migrated.fingerprint, replyId);
    expect(stored.has(legacyKey)).toBe(false);
  });
});

test("unwritable browser storage still preserves multiple follow-up IDs in memory", async () => {
  await withStorage({
    getItem: () => "[]",
    setItem: () => { throw new Error("Storage denied"); },
  }, async () => {
    const sendId = "unwritable-" + crypto.randomUUID();
    const firstText = "First " + crypto.randomUUID();
    const secondText = "Second " + crypto.randomUUID();
    const first = await pendingQueuedFollowupRequest(sendId, firstText);
    const second = await pendingQueuedFollowupRequest(sendId, secondText);
    expect((await pendingQueuedFollowupRequest(sendId, firstText)).replyId).toBe(first.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, secondText)).replyId).toBe(second.replyId);
  });
});
