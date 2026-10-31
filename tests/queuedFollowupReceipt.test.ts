import { expect, test } from "bun:test";
import {
  findQueuedFollowupReceiptState,
  queuedFollowupReceiptState,
} from "../src/ui/exactReplyReceipt";

const sendId = "manual-aabbccdd";
const replyId = "f".repeat(32);
const text = "Test follow-up";
const receipt = {
  reply_id: replyId,
  send_id: sendId,
  user_text: text,
  queued_by_user: true,
  status: "queued",
};

test("queued follow-up receipts require the exact user-clicked identity", () => {
  expect(queuedFollowupReceiptState(receipt, sendId, replyId, text)).toBe("accepted");
  for (const status of [
    "queued",
    "prepared",
    "preflight_failed",
    "dispatching",
    "accepted",
    "generating",
    "completed",
    "interrupted",
    "unavailable",
  ]) {
    expect(queuedFollowupReceiptState({ ...receipt, status }, sendId, replyId, text)).toBe(
      "accepted",
    );
  }
  expect(
    queuedFollowupReceiptState({ ...receipt, status: "outcome_unknown" }, sendId, replyId, text),
  ).toBe("uncertain");
  expect(
    queuedFollowupReceiptState({ ...receipt, queued_by_user: false }, sendId, replyId, text),
  ).toBe("invalid");
  expect(queuedFollowupReceiptState({ ...receipt, send_id: "other" }, sendId, replyId, text)).toBe(
    "invalid",
  );
  expect(
    queuedFollowupReceiptState({ ...receipt, user_text: "other" }, sendId, replyId, text),
  ).toBe("invalid");
  expect(queuedFollowupReceiptState({ ...receipt, reply_id: "other" }, sendId, replyId, text)).toBe(
    "invalid",
  );
  expect(
    queuedFollowupReceiptState({ ...receipt, status: "bad-state" }, sendId, replyId, text),
  ).toBe("invalid");
});

test("reconciles only the exact locally stored queued follow-up, without sending", async () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  const seen: string[] = [];
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async (url: string, init: RequestInit) => {
      seen.push(init.method ?? "GET");
      expect(url).toBe("./api/results/" + sendId + "/turns");
      expect(init.cache).toBe("no-store");
      return Response.json({
        turns: [
          { ...receipt, reply_id: "another" },
          { ...receipt, status: "completed" },
        ],
      });
    },
  });
  try {
    expect(await findQueuedFollowupReceiptState(sendId, replyId, text)).toBe("accepted");
    expect(seen).toEqual(["GET"]);
  } finally {
    if (previous) Object.defineProperty(globalThis, "fetch", previous);
    else Reflect.deleteProperty(globalThis, "fetch");
  }
});

test("unavailable local receipts remain unresolved, never accepted by default", async () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async () => {
      throw new Error("Local SQLite temporarily unavailable");
    },
  });
  try {
    expect(await findQueuedFollowupReceiptState(sendId, replyId, text)).toBeNull();
  } finally {
    if (previous) Object.defineProperty(globalThis, "fetch", previous);
    else Reflect.deleteProperty(globalThis, "fetch");
  }
});
