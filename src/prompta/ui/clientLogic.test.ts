import { describe, expect, test } from "bun:test";

import {
  matchingOptimisticConversation,
  parseScheduleSlashCommand,
} from "./clientLogic";

describe("optimistic new-chat reconciliation", () => {
  test("merges the client-first row when SSE returns the real chat", () => {
    const matched = matchingOptimisticConversation(
      [
        {
          id: "WEB:real-chat",
          prompt: "fix the sidebar",
          created_at: 1_005,
        },
      ],
      {
        message: "fix the sidebar",
        createdAt: 1_000,
      },
    );

    expect(matched?.id).toBe("WEB:real-chat");
  });

  test("does not merge an older chat that happens to have the same prompt", () => {
    const matched = matchingOptimisticConversation(
      [
        {
          id: "WEB:old-chat",
          prompt: "fix the sidebar",
          created_at: 900,
        },
      ],
      {
        message: "fix the sidebar",
        createdAt: 1_000,
      },
    );

    expect(matched).toBeNull();
  });

  test("prefers the conversation id once the send job has it", () => {
    const matched = matchingOptimisticConversation(
      [
        { id: "WEB:real-chat", prompt: "server prompt", created_at: 500 },
      ],
      {
        conversationId: "WEB:real-chat",
        message: "client prompt",
        createdAt: 1_000,
      },
    );

    expect(matched?.id).toBe("WEB:real-chat");
  });
});

describe("/every", () => {
  test("defaults bare numbers to minutes", () => {
    expect(parseScheduleSlashCommand("/every 30 fix bugs")).toEqual({
      intervalMinutes: 30,
      prompt: "fix bugs",
    });
  });

  test("supports hour units", () => {
    expect(parseScheduleSlashCommand("/every 2h review failures")).toEqual({
      intervalMinutes: 120,
      prompt: "review failures",
    });
  });

  test("returns usage for malformed commands", () => {
    expect(parseScheduleSlashCommand("/every tomorrow fix bugs")).toEqual({
      error: "Use /every <minutes> <prompt>, for example: /every 30 fix bugs",
    });
  });
});
