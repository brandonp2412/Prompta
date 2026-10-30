import { expect, test } from "bun:test";
import { acknowledgeFreshQueueRequest, freshQueueRequest } from "../src/ui/freshQueueReceipt";

test("fresh-chat receipt capacity preserves every unconfirmed request ID", async () => {
  const existing = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const stored = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => { stored.set(key, value); },
    },
  });
  try {
    await freshQueueRequest("warmup " + crypto.randomUUID(), [], "capacity-test");
    const key = "prompta.pending-fresh-requests.v1";
    const entries = Array.from({ length: 1024 }, (_, index) => ({
      fingerprint: index.toString(16).padStart(64, "0"),
      requestId: index.toString(16).padStart(32, "0"),
      createdAt: Date.now(),
    }));
    const original = JSON.stringify(entries);
    stored.set(key, original);
    const prompt = "New unique prompt " + crypto.randomUUID();
    await expect(freshQueueRequest(prompt, [], "capacity-test")).rejects.toThrow("at capacity");
    expect(stored.get(key)).toBe(original);
    acknowledgeFreshQueueRequest(entries[0]!.fingerprint, entries[0]!.requestId);
    const admitted = await freshQueueRequest(prompt, [], "capacity-test");
    expect(admitted.requestId).toHaveLength(32);
    expect(JSON.stringify([...stored.values()])).not.toContain(prompt);
  } finally {
    if (existing) Object.defineProperty(globalThis, "localStorage", existing);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
