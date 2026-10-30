import { expect, test } from "bun:test";
import { freshQueueRequest } from "../src/ui/freshQueueReceipt";
import { pendingExactReplyRequest } from "../src/ui/pendingExactReply";

async function fingerprint(values: unknown[]): Promise<string> {
  const hash = new Uint8Array(await crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(JSON.stringify(values)),
  ));
  return Array.from(hash, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

test("a long-unconfirmed receipt never silently expires into a duplicate send", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    },
  });
  try {
    // Ensure earlier storage-denial tests do not leave the modules in memory-only mode.
    await freshQueueRequest("warmup " + crypto.randomUUID(), []);
    await pendingExactReplyRequest("warmup", "conv", "parent", crypto.randomUUID());
    const createdAt = Date.now() - 400 * 24 * 60 * 60 * 1000;
    const prompt = "Old uncertain fresh chat " + crypto.randomUUID();
    const freshId = crypto.randomUUID().replaceAll("-", "");
    values.set("prompta.pending-fresh-requests.v1", JSON.stringify([{
      fingerprint: await fingerprint(["chat", prompt, []]), requestId: freshId, createdAt,
    }]));
    const replyText = "Old uncertain exact reply " + crypto.randomUUID();
    const replyId = crypto.randomUUID().replaceAll("-", "");
    values.set("prompta.pending-exact-replies.v1", JSON.stringify([{
      fingerprint: await fingerprint(["send", "conversation", "parent", replyText]), replyId, createdAt,
    }]));
    expect((await freshQueueRequest(prompt, [])).requestId).toBe(freshId);
    expect((await pendingExactReplyRequest("send", "conversation", "parent", replyText)).replyId).toBe(replyId);
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
