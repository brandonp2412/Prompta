import { expect, test } from "bun:test";
import {
  acknowledgeExactReplyRequest,
  pendingExactReplyRequest,
} from "../src/ui/pendingExactReply";

test("an exact reply keeps its durable ID until a confirmed receipt", async () => {
  const stored = new Map<string, string>();
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => { stored.set(key, value); },
    },
  });
  try {
    const text = "Private exact-branch response " + crypto.randomUUID();
    const first = await pendingExactReplyRequest("send-1", "conversation-1", "parent-1", text);
    const retry = await pendingExactReplyRequest("send-1", "conversation-1", "parent-1", text);
    const otherParent = await pendingExactReplyRequest("send-1", "conversation-1", "parent-2", text);
    const otherText = await pendingExactReplyRequest("send-1", "conversation-1", "parent-1", text + " updated");
    expect(retry.replyId).toBe(first.replyId);
    expect(retry.reused).toBe(true);
    expect(otherParent.replyId).not.toBe(first.replyId);
    expect(otherText.replyId).not.toBe(first.replyId);
    expect(JSON.stringify([...stored.values()])).not.toContain(text);

    acknowledgeExactReplyRequest(first.fingerprint, first.replyId);
    const later = await pendingExactReplyRequest("send-1", "conversation-1", "parent-1", text);
    expect(later.replyId).not.toBe(first.replyId);
    const stillPending = await pendingExactReplyRequest("send-1", "conversation-1", "parent-2", text);
    expect(stillPending.replyId).toBe(otherParent.replyId);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("storage refusal preserves a retry ID in memory instead of trusting stale disk data", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: () => "[]",
      setItem: () => { throw new Error("Quota exceeded"); },
    },
  });
  try {
    const text = "Unsaved browser state " + crypto.randomUUID();
    const first = await pendingExactReplyRequest("send-unwritable", "conversation", "parent", text);
    const retry = await pendingExactReplyRequest("send-unwritable", "conversation", "parent", text);
    expect(retry.replyId).toBe(first.replyId);
    expect(retry.reused).toBe(true);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
