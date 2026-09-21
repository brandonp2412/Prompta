import { describe, expect, test } from "bun:test";

import {
  composerHasContent,
  conversationIdFromHash,
  matchingOptimisticConversation,
  matchingPendingReplyMessageIndex,
  messageAgeText,
  messageTimestampMillis,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  pendingConversationDisplayId,
  pendingConversationSends,
  promotePinnedConversationId,
  pendingSendActivity,
  preserveSidebarChatOrder,
  shouldRenderNewChatView,
  shouldShowStopAction,
  shouldProbeHistoricalActivity,
  postJsonRequest,
  pythonToolCallCode,
  replaceChatGptRichMarkers,
  sidebarChatPreviewText,
  sidebarPreviewText,
  toolCallDisplayName,
  toolCallHasUsefulDetail,
  toolCallIsInvocationPlaceholder,
  toolCallSummary,
  toolCallTimestampMillis,
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

describe("sidebar ordering", () => {
  test("keeps existing chats in place when server activity order changes", () => {
    const previous = [
      { id: "chat-a", updated_at: 100 },
      { id: "chat-b", updated_at: 90 },
      { id: "chat-c", updated_at: 80 },
    ];
    const incoming = [
      { id: "chat-c", updated_at: 130 },
      { id: "chat-a", updated_at: 120 },
      { id: "chat-b", updated_at: 110 },
    ];

    expect(preserveSidebarChatOrder(previous, incoming).map((chat) => chat.id)).toEqual([
      "chat-a",
      "chat-b",
      "chat-c",
    ]);
  });

  test("puts genuinely new chats ahead without shuffling retained chats", () => {
    const previous = [
      { id: "chat-a" },
      { id: "chat-b" },
      { id: "chat-c" },
    ];
    const incoming = [
      { id: "new-2" },
      { id: "chat-c" },
      { id: "new-1" },
      { id: "chat-a" },
      { id: "chat-b" },
    ];

    expect(preserveSidebarChatOrder(previous, incoming).map((chat) => chat.id)).toEqual([
      "new-2",
      "new-1",
      "chat-a",
      "chat-b",
      "chat-c",
    ]);
  });

  test("drops chats that are no longer in the current result set", () => {
    const previous = [{ id: "chat-a" }, { id: "chat-b" }, { id: "chat-c" }];
    const incoming = [{ id: "chat-c" }, { id: "chat-a" }];

    expect(preserveSidebarChatOrder(previous, incoming).map((chat) => chat.id)).toEqual([
      "chat-a",
      "chat-c",
    ]);
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

  test("reconciles one newly seen matching conversation when clocks cannot be compared", () => {
    const matched = matchingOptimisticConversation(
      [
        { id: "WEB:known-chat", prompt: "older prompt" },
        { id: "WEB:new-chat", prompt: "  fix   the sidebar  " },
      ],
      {
        message: "fix the sidebar",
      },
      new Set(["WEB:known-chat"]),
    );

    expect(matched?.id).toBe("WEB:new-chat");
  });

  test("does not reconcile ambiguous newly seen matching conversations", () => {
    const matched = matchingOptimisticConversation(
      [
        { id: "WEB:new-a", prompt: "fix the sidebar" },
        { id: "WEB:new-b", prompt: "fix the sidebar" },
      ],
      {
        message: "fix the sidebar",
      },
      new Set(["WEB:known-chat"]),
    );

    expect(matched).toBeNull();
  });
});

describe("pending new-chat view rendering", () => {
  test("forces a render when returning to an unchanged pending new chat", () => {
    const fingerprint = '["send-1","hello","running"]';
    expect(shouldRenderNewChatView(true, fingerprint, fingerprint)).toBe(true);
  });

  test("still skips redundant renders while already viewing the same pending chat", () => {
    const fingerprint = '["send-1","hello","running"]';
    expect(shouldRenderNewChatView(false, fingerprint, fingerprint)).toBe(false);
    expect(shouldRenderNewChatView(false, fingerprint, 'older')).toBe(true);
  });
});

describe("pending chat pin promotion", () => {
  test("uses the optimistic pending id before ChatGPT assigns a conversation id", () => {
    expect(pendingConversationDisplayId({
      clientId: "client-1",
      conversationId: "",
    })).toBe("pending-new-client-1");
  });

  test("moves a pending pin to the real ChatGPT conversation id", () => {
    const pins = new Set(["pending-new-client-1", "other-chat"]);
    const pending = {
      clientId: "client-1",
      conversationId: "",
    };

    expect(promotePinnedConversationId(pins, pending, "WEB:real-chat")).toBe(true);
    expect(Array.from(pins).sort()).toEqual(["WEB:real-chat", "other-chat"]);
  });

  test("leaves unrelated pins unchanged", () => {
    const pins = new Set(["other-chat"]);
    const pending = {
      clientId: "client-1",
      conversationId: "",
    };

    expect(promotePinnedConversationId(pins, pending, "WEB:real-chat")).toBe(false);
    expect(Array.from(pins)).toEqual(["other-chat"]);
  });
});

describe("pending new-chat selection", () => {
  test("exposes the optimistic first message after the real conversation id appears", () => {
    const pending = {
      clientId: "client-1",
      sendId: "send-1",
      conversationId: "WEB:new-chat",
      message: "show this immediately",
      createdAt: 1_000,
    };

    expect(pendingConversationSends("WEB:new-chat", [], pending)).toEqual([pending]);
    expect(pendingConversationSends("WEB:other-chat", [], pending)).toEqual([]);
  });

  test("does not duplicate a pending new send already promoted into replies", () => {
    const pending = {
      clientId: "client-1",
      sendId: "send-1",
      conversationId: "WEB:new-chat",
      message: "show this immediately",
      createdAt: 1_000,
    };

    expect(pendingConversationSends("WEB:new-chat", [pending], pending)).toEqual([pending]);
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

  test("formats compact elapsed durations for message timestamps", () => {
    const now = 2_000_000_000_000;
    expect(messageAgeText(now - 10_000, now)).toBe("now");
    expect(messageAgeText(now - 4 * 60_000, now)).toBe("4m ago");
    expect(messageAgeText(now - 3 * 3_600_000, now)).toBe("3h ago");
    expect(messageAgeText(now - 8 * 86_400_000, now)).toBe("1w ago");
  });
});

describe("pending send activity", () => {
  test("shows immediate sending feedback before the server returns a send id", () => {
    expect(pendingSendActivity("queued", false)).toEqual({
      label: "sending",
      statusText: "Sending…",
    });
  });

  test("distinguishes queued work from a running ChatGPT send", () => {
    expect(pendingSendActivity("queued", true)).toEqual({
      label: "queued",
      statusText: "Queued in Prompta…",
    });
    expect(pendingSendActivity("running", true)).toEqual({
      label: "waiting",
      statusText: "Waiting for ChatGPT…",
    });
  });

  test("shows rate-limit backoff without turning the send into a failure", () => {
    expect(pendingSendActivity("rate_limited", true, 300)).toEqual({
      label: "rate limited · retry in 5m",
      statusText: "Rate limited — backing off; retrying automatically in 5m.",
    });
  });

  test("counts rate-limit backoff down from the absolute retry deadline", () => {
    expect(pendingSendActivity("rate_limited", true, 300, 1_300, 1_180)).toEqual({
      label: "rate limited · retry in 2m",
      statusText: "Rate limited — backing off; retrying automatically in 2m.",
    });
    expect(pendingSendActivity("rate_limited", true, 300, 1_300, 1_301)).toEqual({
      label: "rate limited · retrying now",
      statusText: "Rate limited — backoff elapsed; retrying now…",
    });
  });

  test("keeps waiting after send acceptance until a response is observed", () => {
    expect(pendingSendActivity("succeeded", true)).toEqual({
      label: "waiting",
      statusText: "Waiting for ChatGPT…",
    });
  });

  test("shows transient retry backoff and stops on terminal queue failures", () => {
    expect(pendingSendActivity("retrying", true, 4, 1_004, 1_000)).toEqual({
      label: "retrying · <1m",
      statusText: "Send failed transiently — retrying automatically in <1m.",
    });
    expect(pendingSendActivity("failed", true)).toBeNull();
    expect(pendingSendActivity("dead_lettered", true)).toBeNull();
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

  test("accepts a durable reply timestamp slightly before the client clock", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 995,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
      },
    );

    expect(matchedIndex).toBe(0);
  });

  test("normalizes milliseconds and whitespace while reconciling replies", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep   fixing bugs",
          created_at: 1_700_000_002_000,
        },
      ],
      {
        message: " keep fixing   bugs ",
        createdAt: 1_700_000_000,
      },
    );

    expect(matchedIndex).toBe(0);
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



describe("historical activity probing", () => {
  test("probes interrupted chats because they may still be live in ChatGPT", () => {
    expect(shouldProbeHistoricalActivity("interrupted")).toBe(true);
  });

  test("does not probe chats whose activity state is already known", () => {
    expect(shouldProbeHistoricalActivity("active")).toBe(false);
    expect(shouldProbeHistoricalActivity("complete")).toBe(false);
  });
});

describe("composer primary action", () => {
  test("keeps Stop as the primary action for an active existing chat with an empty composer", () => {
    expect(shouldShowStopAction("active", false, false)).toBe(true);
  });

  test("switches an active chat from Stop to Send once the composer has content", () => {
    expect(shouldShowStopAction("active", false, true)).toBe(false);
  });

  test("does not show Stop for completed or brand-new chats", () => {
    expect(shouldShowStopAction("complete", false, false)).toBe(false);
    expect(shouldShowStopAction("active", true, false)).toBe(false);
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

describe("/add", () => {
  test("defaults bare numbers to minutes", () => {
    expect(parseScheduleSlashCommand("/add 30 fix bugs")).toEqual({
      intervalMinutes: 30,
      prompt: "fix bugs",
    });
  });

  test.each([
    ["/add 30s check quickly", 0.5],
    ["/add 10 seconds check quickly", 1 / 6],
    ["/add 15 min review failures", 15],
    ["/add 1.5 hours review failures", 90],
    ["/add 2h review failures", 120],
    ["/add 1 day review failures", 1440],
    ["/add 2d review failures", 2880],
  ])("supports useful interval units: %s", (command, intervalMinutes) => {
    expect(parseScheduleSlashCommand(command)).toEqual({
      intervalMinutes,
      prompt: command.includes("check quickly") ? "check quickly" : "review failures",
    });
  });

  test("returns usage for malformed commands", () => {
    expect(parseScheduleSlashCommand("/add tomorrow fix bugs")).toEqual({
      error:
        "Use /add <interval> <prompt>, for example: /add 30 fix bugs or /add 2h review failures",
    });
  });

  test("rejects intervals shorter than six seconds", () => {
    expect(parseScheduleSlashCommand("/add 5s fix bugs")).toEqual({
      error: "Schedule interval must be at least 6 seconds.",
    });
  });

  test("rejects intervals longer than thirty days", () => {
    expect(parseScheduleSlashCommand("/add 31d fix bugs")).toEqual({
      error: "Schedule interval cannot exceed 30 days.",
    });
  });

  test("accepts command names case-insensitively", () => {
    expect(parseScheduleSlashCommand("/ADD 45 review failures")).toEqual({
      intervalMinutes: 45,
      prompt: "review failures",
    });
  });

  test("keeps /every as a compatibility alias", () => {
    expect(parseScheduleSlashCommand("/every 30 fix bugs")).toEqual({
      intervalMinutes: 30,
      prompt: "fix bugs",
    });
  });

  test("does not treat longer slash commands as /add", () => {
    expect(parseScheduleSlashCommand("/address say hello")).toBeNull();
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


  test("falls back to the original prompt when the latest message is tool-only", () => {
    expect(sidebarChatPreviewText(
      "```tool:Nox Python MCP · execute_python\n{\"arguments\":{}}\n```",
      "Fix the chat sidebar preview",
    )).toBe("Fix the chat sidebar preview");
  });

  test("prefers real assistant prose over the original prompt", () => {
    expect(sidebarChatPreviewText(
      "Working on it ```tool:Shell\n{}\n```",
      "Fix the chat sidebar preview",
    )).toBe("Working on it");
  });

describe("tool call display cleanup", () => {
  test("drops ChatGPT tool-list chrome instead of presenting it as a tool", () => {
    expect(toolCallDisplayName("Open tool call list")).toBe("");
    expect(toolCallDisplayName("cot-v5-tool-icon-pile")).toBe("");
    expect(toolCallHasUsefulDetail("Open tool call list\ncot-v5-tool-icon-pile")).toBe(false);
    expect(toolCallIsInvocationPlaceholder("Called tool")).toBe(true);
  });

  test("keeps actual connector names and useful details", () => {
    expect(toolCallDisplayName("Nox Python MCP")).toBe("Nox Python MCP");
    expect(toolCallHasUsefulDetail("execute_python\nHOST nox")).toBe(true);
  });

  test("extracts ChatGPT reasoning titles for collapsed tool summaries", () => {
    expect(toolCallSummary(JSON.stringify({
      summary: "Inspecting Tool Call Ordering in ChatGPT DOM",
      arguments: { pageId: 5 },
    }))).toBe("Inspecting Tool Call Ordering in ChatGPT DOM");
    expect(toolCallSummary(JSON.stringify({ arguments: { pageId: 5 } }))).toBe("");
  });

  test("extracts tool call timestamps in seconds or milliseconds", () => {
    expect(toolCallTimestampMillis(JSON.stringify({ created_at: 1_700_000_000 }))).toBe(1_700_000_000_000);
    expect(toolCallTimestampMillis(JSON.stringify({ timestamp: 1_700_000_000_123 }))).toBe(1_700_000_000_123);
    expect(toolCallTimestampMillis(JSON.stringify({ created_at: 1e30 }))).toBeNull();
    expect(toolCallTimestampMillis(JSON.stringify({ arguments: { pageId: 5 } }))).toBeNull();
  });

  test("extracts only Python source from Nox and Glass MCP tool payloads", () => {
    const nox = JSON.stringify({
      arguments: {
        code: "from pathlib import Path\nprint(Path.cwd())",
        cwd: "/home/brandon/prompta",
      },
      status: "completed",
      result: { stdout: "/home/brandon/prompta\n" },
    });
    const glass = JSON.stringify({
      arguments: JSON.stringify({
        code: "import socket\nprint(socket.gethostname())",
        timeout_seconds: 120,
      }),
      status: "completed",
    });

    expect(pythonToolCallCode("Nox Python MCP · execute_python", nox))
      .toBe("from pathlib import Path\nprint(Path.cwd())");
    expect(pythonToolCallCode("Glass · execute_python", glass))
      .toBe("import socket\nprint(socket.gethostname())");
  });

  test("strips leading blank lines from Python MCP code for display only", () => {
    const payload = JSON.stringify({
      arguments: {
        code: "\n \t\n  print('keeps indentation')\n",
      },
    });

    expect(pythonToolCallCode("Nox Python MCP · execute_python", payload))
      .toBe("  print('keeps indentation')\n");
  });

  test("does not reinterpret non-Python MCP JSON as Python", () => {
    expect(pythonToolCallCode(
      "GitHub · get_issue",
      JSON.stringify({ arguments: { code: "not python" } }),
    )).toBe("");
  });
});


describe("ChatGPT rich-text markers", () => {
  const start = "\uE200";
  const end = "\uE201";
  const sep = "\uE202";

  test("turns native URL markers into renderer-controlled links", () => {
    const input = `Deployed ${start}url${sep}Commit e5612bc${sep}https://github.com/brandonp2412/Prompta/commit/e5612bc${end}.`;
    expect(replaceChatGptRichMarkers(
      input,
      (label, url) => `<a href="${url}">${label}</a>`,
    )).toBe(
      'Deployed <a href="https://github.com/brandonp2412/Prompta/commit/e5612bc">Commit e5612bc</a>.',
    );
  });

  test("removes native citation markers without leaking internal source ids", () => {
    const input = `K-9 supports this.${start}cite${sep}turn158675search6${sep}turn158675search3${end}`;
    expect(replaceChatGptRichMarkers(input)).toBe("K-9 supports this.");
  });

  test("hides incomplete streaming markers until the closing delimiter arrives", () => {
    expect(replaceChatGptRichMarkers(`Ready ${start}url${sep}Commit`)).toBe("Ready ");
  });

  test("sidebar previews use readable rich-link labels", () => {
    const input = `Fixed in ${start}url${sep}Commit abc1234${sep}https://example.com/commit/abc1234${end}`;
    expect(sidebarPreviewText(input)).toBe("Fixed in Commit abc1234");
  });
});
