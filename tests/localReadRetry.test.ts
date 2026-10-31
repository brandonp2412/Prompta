import { expect, test } from "bun:test";
import { localGet, localReadTimeoutMs } from "../src/ui/localRead";

test("transient local gateway GET failures get exactly one retry", async () => {
  const original = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const outcomes = [503, 200];
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response("", { status: outcomes.shift() ?? 500 });
  }) as typeof fetch;
  try {
    const response = await localGet("./api/results?offset=0");
    expect(response.status).toBe(200);
    expect(calls.map((call) => call.url)).toEqual([
      "./api/results?offset=0",
      "./api/results?offset=0",
    ]);
    expect(calls.every((call) => call.init?.cache === "no-store")).toBe(true);
    expect(calls.every((call) => call.init?.signal instanceof AbortSignal)).toBe(true);
  } finally {
    globalThis.fetch = original;
  }
});

test("client errors and application errors are never replayed", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    return new Response("", { status: 500 });
  }) as typeof fetch;
  try {
    expect((await localGet("./api/results/missing")).status).toBe(500);
    expect(calls).toBe(1);
  } finally {
    globalThis.fetch = original;
  }
});

test("a nearly exhausted read deadline does not start a second GET", async () => {
  const original = globalThis.fetch;
  const originalNow = Date.now;
  let now = 10;
  let calls = 0;
  Date.now = () => now;
  globalThis.fetch = (async () => {
    calls += 1;
    now += localReadTimeoutMs - 100;
    return new Response("", { status: 504 });
  }) as typeof fetch;
  try {
    expect((await localGet("./api/health")).status).toBe(504);
    expect(calls).toBe(1);
  } finally {
    globalThis.fetch = original;
    Date.now = originalNow;
  }
});
