import { describe, expect, test } from "bun:test";

import {
  composerHasContent,
  conversationIdFromHash,
  matchingOptimisticConversation,
  matchingPendingReplyMessageIndex,
  messageTimestampMillis,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  postJsonRequest,
  sidebarPreviewText,
} from "./clientLogic";

describe("conversation hash parsing", () => {
  test("decodes a deep-linked conversation id", () => {
    expect(conversationIdFromHash("#/WEB%3Achat-123")).toBe("WEB:chat-123");
  });

  test("treats a malformed URI hash as no route instead of throwing", () => {
    expect(conversationIdFromHash("#/%E0%A4%A")).toBe("");
  });

  test("accepts hashes with and without a slash", () => {
    expect(conversationIdFromHash("#chat-123")).toBe("chat-123");
    expect(conversationIdFromHash("#/chat-123")).toBe("chat-123");
  });
});

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

  test("matches the timestamp-nearest duplicate prompt", () => {
    const matched = matchingOptimisticConversation(
      [
        { id: "WEB:farther", prompt: "fix the sidebar", created_at: 1_020 },
        { id: "WEB:nearest", prompt: "fix the sidebar", created_at: 1_002 },
      ],
      {
        message: "fix the sidebar",
        createdAt: 1_000,
      },
    );

    expect(matched?.id).toBe("WEB:nearest");
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

  test("does not guess from duplicate prompt text when server timing is missing", () => {
    const matched = matchingOptimisticConversation(
      [
        { id: "WEB:unknown-age", prompt: "fix the sidebar" },
      ],
      {
        message: "fix the sidebar",
        createdAt: 1_000,
      },
    );

    expect(matched).toBeNull();
  });
});

describe("message timestamps", () => {
  test("normalizes seconds and milliseconds", () => {
    expect(messageTimestampMillis(1_700_000_000, null)).toBe(1_700_000_000_000);
    expect(messageTimestampMillis(1_700_000_000_000, null)).toBe(1_700_000_000_000);
  });

  test("falls back to updated_at when created_at is malformed", () => {
    expect(messageTimestampMillis("not-a-date", 1_700_000_000)).toBe(1_700_000_000_000);
  });

  test("rejects invalid and out-of-range timestamps without throwing", () => {
    expect(messageTimestampMillis("not-a-date", Number.MAX_VALUE)).toBeNull();
  });
});

describe("POST request recovery", () => {
  test("times out a stalled request instead of hanging forever", async () => {
    const stalledFetch = ((_: RequestInfo | URL, init?: RequestInit) => (
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      })
    )) as typeof fetch;

    await expect(
      postJsonRequest("api/chats", { message: "hello" }, 1, 10, stalledFetch),
    ).rejects.toThrow("Request timed out");
  });

  test("retries transient fetch failures and returns the successful JSON body", async () => {
    let calls = 0;
    const retryingFetch = (async () => {
      calls += 1;
      if (calls === 1) throw new TypeError("network unavailable");
      return new Response(JSON.stringify({ ok: true, send_id: "send-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    const result = await postJsonRequest(
      "api/chats",
      { message: "hello" },
      2,
      1_000,
      retryingFetch,
    );

    expect(calls).toBe(2);
    expect(result.send_id).toBe("send-1");
  });

  test("rejects malformed JSON from a successful response", async () => {
    const malformedFetch = (async () => (
      new Response("not json", {
        status: 202,
        headers: { "Content-Type": "application/json" },
      })
    )) as typeof fetch;

    await expect(
      postJsonRequest("api/chats", { message: "hello" }, 1, 1_000, malformedFetch),
    ).rejects.toThrow("Prompta returned an invalid response");
  });
});

describe("optimistic reply reconciliation", () => {
  test("accepts a recent durable cached user message", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 1_002,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
    );

    expect(matchedIndex).toBe(0);
  });

  test("does not match an older identical user message", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 900,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
    );

    expect(matchedIndex).toBe(-1);
  });

  test("requires durable timing metadata instead of guessing from duplicate text", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
    );

    expect(matchedIndex).toBe(-1);
  });

  test("matches the timestamp-nearest duplicate reply", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 1_020,
        },
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 1_001,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
    );

    expect(matchedIndex).toBe(1);
  });

  test("does not reuse a cached message already claimed by another pending reply", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 1_002,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
      new Set([0]),
    );

    expect(matchedIndex).toBe(-1);
  });
});

describe("composer content", () => {
  test("rejects an empty composer without attachments", () => {
    expect(composerHasContent("   ", 0)).toBe(false);
  });

  test("accepts an attachment-only message", () => {
    expect(composerHasContent("   ", 1)).toBe(true);
  });

  test("accepts text without attachments", () => {
    expect(composerHasContent("hello", 0)).toBe(true);
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

  test("accepts command names case-insensitively", () => {
    expect(parseScheduleSlashCommand("/EVERY 45 review failures")).toEqual({
      intervalMinutes: 45,
      prompt: "review failures",
    });
  });

  test("does not treat longer slash commands as /every", () => {
    expect(parseScheduleSlashCommand("/everybody say hello")).toBeNull();
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

  test("accepts command names case-insensitively", () => {
    const parsed = parseAtSlashCommand("/AT tomorrow 08:15 ship it", now);
    expect(parsed && !("error" in parsed) ? parsed.runAtEpoch : 0).toBe(
      new Date(2026, 8, 21, 8, 15, 0).getTime() / 1000,
    );
  });

  test("rejects a nonexistent local time during the DST jump", () => {
    const previousTimezone = process.env.TZ;
    process.env.TZ = "Pacific/Auckland";
    try {
      const beforeJump = new Date(2026, 8, 26, 12, 0, 0);
      expect(parseAtSlashCommand("/at 2026-09-27 02:30 impossible", beforeJump)).toEqual({
        error: "Schedule time does not exist in the local timezone.",
      });
    } finally {
      if (previousTimezone === undefined) delete process.env.TZ;
      else process.env.TZ = previousTimezone;
    }
  });

  test("does not treat longer slash commands as /at", () => {
    expect(parseAtSlashCommand("/atlas tomorrow 08:15", now)).toBeNull();
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
