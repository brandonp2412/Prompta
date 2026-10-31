import { expect, test } from "bun:test";
import { localGet } from "../src/ui/localRead";

test("failed retry preserves the first gateway response for a read-only request", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    if (calls === 1) return new Response("Gateway temporarily unavailable", { status: 503 });
    throw new TypeError("Retry connection dropped");
  }) as typeof fetch;
  try {
    const response = await localGet("./api/results");
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("Gateway temporarily unavailable");
    expect(calls).toBe(2);
  } finally {
    globalThis.fetch = original;
  }
});

test("two transport failures surface the retry error", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    throw new TypeError("Network unavailable");
  }) as typeof fetch;
  try {
    await expect(localGet("./api/health")).rejects.toThrow("Network unavailable");
    expect(calls).toBe(2);
  } finally {
    globalThis.fetch = original;
  }
});
