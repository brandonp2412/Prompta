import { expect, test } from "bun:test";
import {
  findFreshQueueReceipt,
  findFreshQueueReceiptStatus,
} from "../src/ui/freshQueueReceipt";

test("fresh receipt lookups expose terminal status without sending again", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  const requestId = "a".repeat(32);
  const urls: string[] = [];
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async (url: string, options: RequestInit) => {
      urls.push(url);
      expect(options.method).not.toBe("POST");
      return new Response(JSON.stringify({
        send_id: "manual-" + requestId,
        status: "outcome_unknown",
      }), { headers: { "content-type": "application/json" } });
    },
  });
  try {
    expect(await findFreshQueueReceiptStatus(requestId)).toEqual({
      sendId: "manual-" + requestId, status: "outcome_unknown",
    });
    expect(await findFreshQueueReceipt(requestId)).toBe("manual-" + requestId);
    expect(urls).toEqual(Array(2).fill("./api/chats/requests/" + requestId));
  } finally {
    if (original) Object.defineProperty(globalThis, "fetch", original);
    else Reflect.deleteProperty(globalThis, "fetch");
  }
});

test("mismatched server receipts cannot be mistaken for accepted sends", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async () => new Response(JSON.stringify({
      send_id: "manual-" + "b".repeat(32), status: "succeeded",
    }), { headers: { "content-type": "application/json" } }),
  });
  try {
    expect(await findFreshQueueReceiptStatus("a".repeat(32))).toBeNull();
  } finally {
    if (original) Object.defineProperty(globalThis, "fetch", original);
    else Reflect.deleteProperty(globalThis, "fetch");
  }
});
