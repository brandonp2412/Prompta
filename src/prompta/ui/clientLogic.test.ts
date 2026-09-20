import { describe, expect, test } from "bun:test";

import {
  matchingOptimisticConversation,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  sidebarPreviewText,
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


describe("/at", () => {
  const now = new Date(2026, 8, 20, 16, 0, 0);

  test("parses an absolute local date and time", () => {
    expect(parseAtSlashCommand("/at 2026-09-21 09:30 review failures", now)).toEqual({
      runAtEpoch: new Date(2026, 8, 21, 9, 30, 0).getTime() / 1000,
      runAtLabel: new Date(2026, 8, 21, 9, 30, 0).toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
      prompt: "review failures",
    });
  });

  test("supports tomorrow in local time", () => {
    const parsed = parseAtSlashCommand("/at tomorrow 08:15 ship it", now);
    expect(parsed && !("error" in parsed) ? parsed.runAtEpoch : 0).toBe(
      new Date(2026, 8, 21, 8, 15, 0).getTime() / 1000,
    );
  });

  test("rejects times in the past", () => {
    expect(parseAtSlashCommand("/at today 15:00 too late", now)).toEqual({
      error: "Schedule time must be in the future.",
    });
  });
});


describe("sidebar previews", () => {
  test("removes fenced tool activity while keeping useful prose", () => {
    expect(sidebarPreviewText(
      "Fixed ```tool:Open tool call list Open tool call list ```",
    )).toBe("Fixed");
  });

  test("removes multiline tool fences and normalizes whitespace", () => {
    expect(sidebarPreviewText(
      "Before  ```tool-call: shell\n{\"cmd\":\"true\"}\n```  after",
    )).toBe("Before after");
  });
});
