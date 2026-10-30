import { expect, test } from "bun:test";
import { freshQueueRequest } from "../src/ui/freshQueueReceipt";
import { pendingExactReplyRequest } from "../src/ui/pendingExactReply";

const freshKey = "prompta.pending-fresh-requests.v1";
const replyKey = "prompta.pending-exact-replies.v1";

async function fingerprint(values: unknown[]): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(values));
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function withStorage(action: (stored: Map<string, string>) => Promise<void>) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const stored = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => { stored.set(key, value); },
    },
  });
  try {
    await action(stored);
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
}

test("fresh chat never silently discards corrupted unresolved receipts", async () => {
  await withStorage(async (stored) => {
    await freshQueueRequest("warmup " + crypto.randomUUID(), []);
    const prompt = "Confidential fresh prompt " + crypto.randomUUID();
    for (const corrupt of [
      "{",
      '{"records":[]}',
      JSON.stringify([{ fingerprint: "a".repeat(64), createdAt: Date.now() }]),
    ]) {
      stored.set(freshKey, corrupt);
      await expect(freshQueueRequest(prompt, [])).rejects.toThrow("Unresolved chat receipts are unreadable");
      expect(stored.get(freshKey)).toBe(corrupt);
    }

    const requestId = crypto.randomUUID().replaceAll("-", "");
    stored.set(freshKey, JSON.stringify([{
      fingerprint: await fingerprint(["chat", prompt, []]),
      requestId,
      createdAt: Date.now() + 24 * 60 * 60 * 1000,
    }]));
    const reused = await freshQueueRequest(prompt, []);
    expect(reused).toMatchObject({ requestId, reused: true });
    expect(stored.get(freshKey)).not.toContain(prompt);
  });
});

test("exact-branch replies fail closed on corrupt receipts and survive forward clock skew", async () => {
  await withStorage(async (stored) => {
    await pendingExactReplyRequest("warmup", "conversation", "parent", crypto.randomUUID());
    const replyText = "Confidential reply " + crypto.randomUUID();
    const sendId = "send-1";
    const conversationId = "conversation-1";
    const parentId = "parent-1";
    for (const corrupt of [
      "null",
      "[",
      JSON.stringify([{ fingerprint: "b".repeat(64), replyId: "not-a-uuid", createdAt: Date.now() }]),
    ]) {
      stored.set(replyKey, corrupt);
      await expect(pendingExactReplyRequest(sendId, conversationId, parentId, replyText))
        .rejects.toThrow("Unresolved reply receipts are unreadable");
      expect(stored.get(replyKey)).toBe(corrupt);
    }

    const replyId = crypto.randomUUID().replaceAll("-", "");
    stored.set(replyKey, JSON.stringify([{
      fingerprint: await fingerprint([sendId, conversationId, parentId, replyText]),
      replyId,
      createdAt: Date.now() + 24 * 60 * 60 * 1000,
    }]));
    const reused = await pendingExactReplyRequest(sendId, conversationId, parentId, replyText);
    expect(reused).toMatchObject({ replyId, reused: true });
    expect(stored.get(replyKey)).not.toContain(replyText);
  });
});
