import { expect, test } from "bun:test";
import { chatDotStatus } from "../src/ui/resultFormatting";

test("user-queued follow-ups stay blue while fresh queued chats stay grey", () => {
  expect(chatDotStatus({ status: "queued", queued_followup: true })).toBe("generating");
  expect(chatDotStatus({ status: "queued", queued_followup: false })).toBe("queued");
  expect(chatDotStatus({ status: "queued" })).toBe("queued");
});

test("follow-up completion and attention override pending activity", () => {
  expect(chatDotStatus({ status: "completed", queued_followup: false })).toBe("completed");
  expect(chatDotStatus({ status: "interrupted", needs_attention: true })).toBe("interrupted");
  expect(chatDotStatus({ status: "queued", queued_followup: true, needs_attention: true })).toBe(
    "interrupted",
  );
});
