import { expect, test } from "bun:test";
import {
  acknowledgeExactReplyRequest,
  pendingQueuedFollowupRequest,
} from "../src/ui/pendingExactReply";

test("receipt storage fails closed instead of evicting an unconfirmed send", async () => {
  const existing = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const stored = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => { stored.set(key, value); },
      removeItem: (key: string) => { stored.delete(key); },
    },
  });
  try {
    // A successful write also restores this module from any earlier simulated
    // storage-denial test before we seed the full persistent ledger.
    await pendingQueuedFollowupRequest("warmup-" + crypto.randomUUID(), "warmup");
    const key = "prompta.pending-exact-replies.v1";
    const entries = Array.from({ length: 1024 }, (_, index) => ({
      fingerprint: index.toString(16).padStart(64, "0"),
      replyId: index.toString(16).padStart(32, "0"),
      createdAt: Date.now(),
    }));
    const original = JSON.stringify(entries);
    stored.set(key, original);
    const sendId = "full-" + crypto.randomUUID();
    const text = "Unconfirmed extra message";
    await expect(pendingQueuedFollowupRequest(sendId, text)).rejects.toThrow("at capacity");
    expect(stored.get(key)).toBe(original);
    acknowledgeExactReplyRequest(entries[0]!.fingerprint, entries[0]!.replyId);
    expect((await pendingQueuedFollowupRequest(sendId, text)).replyId).toHaveLength(32);
    expect(JSON.stringify([...stored.values()])).not.toContain(text);
  } finally {
    if (existing) Object.defineProperty(globalThis, "localStorage", existing);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
