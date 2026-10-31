import { expect, test } from "bun:test";
import { freshQueueRequest } from "../src/ui/freshQueueReceipt";

test("explicit new-chat retry has a separate durable request ID", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    },
  });
  try {
    const prompt = "Failed fresh chat " + crypto.randomUUID();
    const originalRequest = await freshQueueRequest(prompt, []);
    const retryScope = "explicit-retry:manual-" + crypto.randomUUID().replaceAll("-", "");
    const retryRequest = await freshQueueRequest(prompt, [], retryScope);
    expect(retryRequest.requestId).not.toBe(originalRequest.requestId);
    expect(retryRequest.reused).toBe(false);
    const reconciledRetry = await freshQueueRequest(prompt, [], retryScope);
    expect(reconciledRetry.requestId).toBe(retryRequest.requestId);
    expect(reconciledRetry.reused).toBe(true);
    expect((await freshQueueRequest(prompt, [])).requestId).toBe(originalRequest.requestId);
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
