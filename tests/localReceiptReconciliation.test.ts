import { expect, test } from "bun:test";
import { pinReceiptConfirmed, readReceiptConfirmed } from "../src/ui/localReceiptReconciliation";

test("lost read acknowledgments reconcile only an exact persisted revision", async () => {
  const original = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = (async (url: RequestInfo | URL) => {
    urls.push(String(url));
    return Response.json({ send_id: "id-1", last_read_revision: "rev-1" });
  }) as typeof fetch;
  try {
    expect(await readReceiptConfirmed("id-1", "rev-1")).toBe(true);
    expect(await readReceiptConfirmed("id-1", "rev-2")).toBe(false);
    expect(urls).toEqual(["./api/results/id-1", "./api/results/id-1"]);
  } finally { globalThis.fetch = original; }
});

test("pin acknowledgments reconcile both pin and unpin without POST retries", async () => {
  const original = globalThis.fetch;
  const methods: string[] = [];
  globalThis.fetch = (async (_url: RequestInfo | URL, init?: RequestInit) => {
    methods.push(init?.method ?? "GET");
    return Response.json({ items: [{ send_id: "pinned-1" }] });
  }) as typeof fetch;
  try {
    expect(await pinReceiptConfirmed("pinned-1", true)).toBe(true);
    expect(await pinReceiptConfirmed("pinned-1", false)).toBe(false);
    expect(await pinReceiptConfirmed("other", false)).toBe(true);
    expect(methods).toEqual(["GET", "GET", "GET"]);
  } finally { globalThis.fetch = original; }
});

test("failed local receipt reads cannot invent accepted mutations", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response("Gateway unavailable", { status: 500 })) as typeof fetch;
  try {
    expect(await readReceiptConfirmed("id-1", "rev-1")).toBe(false);
    expect(await pinReceiptConfirmed("id-1", true)).toBe(false);
  } finally { globalThis.fetch = original; }
});
