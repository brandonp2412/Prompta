import { describe, expect, test } from "bun:test";

import {
  canMorphPendingMessageNode,
  pendingLongPressMoved,
  shouldHandlePendingLongPress,
} from "./conversationLogic";

describe("pending message long press", () => {
  test("handles touch and coarse pointers without hijacking desktop mouse clicks", () => {
    expect(shouldHandlePendingLongPress("touch", false)).toBe(true);
    expect(shouldHandlePendingLongPress("pen", false)).toBe(true);
    expect(shouldHandlePendingLongPress("mouse", true)).toBe(true);
    expect(shouldHandlePendingLongPress("mouse", false)).toBe(false);
  });

  test("cancels a long press when the pointer turns into a scroll gesture", () => {
    expect(pendingLongPressMoved(10, 10, 18, 18)).toBe(false);
    expect(pendingLongPressMoved(10, 10, 24, 10)).toBe(true);
  });
});

describe("pending message DOM reconciliation", () => {
  test("morphs optimistic user rows into their durable user rows", () => {
    expect(canMorphPendingMessageNode("pending-user-client-1", "user")).toBe(true);
    expect(canMorphPendingMessageNode("pending-user-client-1", "assistant")).toBe(false);
  });

  test("morphs writing activity into the durable assistant response", () => {
    expect(canMorphPendingMessageNode("pending-activity-client-1", "assistant")).toBe(true);
    expect(canMorphPendingMessageNode("pending-activity-client-1", "user")).toBe(false);
  });

  test("never morphs a pending node into an error row", () => {
    expect(canMorphPendingMessageNode("pending-activity-client-1", "assistant", true)).toBe(false);
  });
});
