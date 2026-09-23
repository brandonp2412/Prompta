import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import {
  canMorphPendingMessageNode,
  pendingLongPressMoved,
  shouldHandlePendingLongPress,
} from "./conversationLogic";

const conversationMessagesSource = readFileSync(
  new URL("./ConversationMessages.svelte", import.meta.url),
  "utf8",
);
const appCssSource = readFileSync(new URL("../static/app.css", import.meta.url), "utf8");

describe("pending message long press", () => {
  test("handles touch and coarse pointers without hijacking desktop mouse clicks", () => {
    expect(shouldHandlePendingLongPress("touch", false)).toBe(true);
    expect(shouldHandlePendingLongPress("pen", false)).toBe(true);
    expect(shouldHandlePendingLongPress("mouse", true)).toBe(true);
    expect(shouldHandlePendingLongPress("mouse", false)).toBe(false);
  });

  test("cancels a long press as soon as movement becomes a drag", () => {
    expect(pendingLongPressMoved(10, 10, 18, 18)).toBe(false);
    expect(pendingLongPressMoved(10, 10, 19, 10)).toBe(true);
    expect(pendingLongPressMoved(10, 10, 10, 19)).toBe(true);
  });
});

describe("desktop pending message actions", () => {
  test("keeps edit and delete controls available for queued messages", () => {
    expect(conversationMessagesSource).toContain('aria-label="Edit queued message"');
    expect(conversationMessagesSource).toContain(
      "conversationState.onEdit(String(message.pending_delete_key))",
    );
    expect(conversationMessagesSource).toContain('aria-label="Delete queued message"');
    expect(conversationMessagesSource).toContain(
      "conversationState.onDelete(String(message.pending_delete_key))",
    );
  });

  test("keeps desktop controls out of the coarse-pointer mobile UI", () => {
    expect(appCssSource).toMatch(
      /@media \(hover: none\), \(pointer: coarse\)[\s\S]*?\.pending-message-controls \{\s*display: none;/,
    );
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
