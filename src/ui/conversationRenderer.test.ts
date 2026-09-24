import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { TOOL_CODE_DIFF_FIELD } from "./diffPreview";
import {
  canMorphPendingMessageNode,
  messageDisplayContent,
  pendingLongPressMoved,
  shouldHandlePendingLongPress,
} from "./conversationLogic";

const conversationMessagesSource = readFileSync(
  new URL("./ConversationMessages.svelte", import.meta.url),
  "utf8",
);
const appCssSource = readFileSync(new URL("../static/app.css", import.meta.url), "utf8");

describe("canonical assistant transcript rendering", () => {
  test("renders structured text and tool calls by canonical ordinal instead of grouped cached content", () => {
    const content = messageDisplayContent({
      role: "assistant",
      content: "First text\n\nBetween tools\n\nFirst tool\n\nSecond tool\n\nDone",
      parts_renderable: true,
      parts: [
        { ordinal: 4, kind: "final_text", content: "Done" },
        { ordinal: 1, kind: "tool_call", content: "First tool" },
        { ordinal: 3, kind: "tool_call", content: "Second tool" },
        { ordinal: 0, kind: "assistant_text", content: "First text" },
        { ordinal: 2, kind: "assistant_text", content: "Between tools" },
      ],
    });

    expect(content.indexOf("First text")).toBeLessThan(content.indexOf("First tool"));
    expect(content.indexOf("First tool")).toBeLessThan(content.indexOf("Between tools"));
    expect(content.indexOf("Between tools")).toBeLessThan(content.indexOf("Second tool"));
    expect(content.indexOf("Second tool")).toBeLessThan(content.indexOf("Done"));
  });

  test("attaches a diff only to the canonical tool part with the matching call key", () => {
    const fence = String.fromCharCode(96, 96, 96);
    const first = [fence + "tool:Glass · execute_python", '{"status":"completed"}', fence].join(
      "\n",
    );
    const second = [
      fence + "tool:Glass Serena · serena_repl",
      '{"status":"completed"}',
      fence,
    ].join("\n");
    const content = messageDisplayContent({
      role: "assistant",
      content: first + "\n\n" + second,
      parts_renderable: true,
      parts: [
        { ordinal: 0, kind: "tool_call", tool_call_key: "tool-1", content: first },
        { ordinal: 1, kind: "tool_call", tool_call_key: "tool-2", content: second },
      ],
      tool_calls: [
        {
          call_key: "tool-2",
          code_diff: {
            patch_text: "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new",
            changed_file_count: 1,
            additions: 1,
            deletions: 1,
            truncated: false,
          },
        },
      ],
    });

    expect(content.split(TOOL_CODE_DIFF_FIELD)).toHaveLength(2);
    expect(content.indexOf(TOOL_CODE_DIFF_FIELD)).toBeGreaterThan(
      content.indexOf("Glass Serena · serena_repl"),
    );
    expect(content.slice(0, content.indexOf("Glass Serena · serena_repl"))).not.toContain(
      TOOL_CODE_DIFF_FIELD,
    );
  });

  test("falls back to cached content when canonical parts are absent or not trusted", () => {
    const legacy = "Legacy cached transcript";

    expect(messageDisplayContent({ role: "assistant", content: legacy })).toBe(legacy);
    expect(
      messageDisplayContent({
        role: "assistant",
        content: legacy,
        parts_renderable: false,
        parts: [{ ordinal: 0, content: "Partial structured content" }],
      }),
    ).toBe(legacy);
  });

  test("the Svelte message view consumes canonical display content", () => {
    expect(conversationMessagesSource).toContain(
      "<MarkdownContent source={messageDisplayContent(message)} streaming={streaming(message)} />",
    );
  });
});

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
