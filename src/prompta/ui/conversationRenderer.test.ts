import { describe, expect, test } from "bun:test";

import { canMorphPendingMessageNode } from "./conversationRenderer";

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
