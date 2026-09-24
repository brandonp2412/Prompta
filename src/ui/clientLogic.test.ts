import { describe, expect, test } from "bun:test";

import {
  chatIsBroken,
  chatListRequestUrl,
  clientIdBelongsToSession,
  composerHasContent,
  conversationIdFromHash,
  deleteRequest,
  formatClockTime12Hour,
  formatDailyTime12Hour,
  formatRelativeTime,
  isUnresolvedPendingNewConversation,
  isPostJsonTransportError,
  matchingOptimisticConversation,
  matchingPendingReplyMessageIndex,
  missingPendingConversationSummaries,
  messageAgeText,
  messageTimestampMillis,
  nextSlashCommandIndex,
  parseAtSlashCommand,
  parseScheduleSlashCommand,
  pendingConversationDisplayId,
  pendingConversationStatus,
  pendingConversationSends,
  promotePinnedConversationId,
  pendingSendActivity,
  shouldRenderNewChatView,
  shouldShowStopAction,
  shouldProbeHistoricalActivity,
  shouldRefreshSelectedChat,
  postJsonRequest,
  pythonToolCallCode,
  replaceChatGptRichMarkers,
  sidebarChatCreatedAt,
  sidebarChatLastUserAt,
  sidebarChatIsPending,
  sidebarChatIsSelected,
  sidebarChatMatchesFilters,
  sidebarChatMatchesSearch,
  sidebarChatPreviewText,
  sidebarSearchDelay,
  sidebarHealthNeedsRefresh,
  sidebarSelectedConversationId,
  selectedConversationAfterChatRefresh,
  sidebarPreviewText,
  sortSidebarChats,
  toolCallDisplayName,
  toolCallHasUsefulDetail,
  toolCallIsInvocationPlaceholder,
  toolCallSummary,
  toolCallTimestampMillis,
} from "./clientLogic";

describe("chat list request URL", () => {
  test("keeps pinned chats in the sidebar request even when they are older than the recent limit", () => {
    expect(chatListRequestUrl("", new Set(["WEB:old-chat", "chat-2"]))).toBe(
      "api/chats?include=WEB%3Aold-chat&include=chat-2",
    );
  });

  test("search does not force unrelated pinned chats into filtered results", () => {
    expect(chatListRequestUrl("Kite work", new Set(["WEB:old-chat"]))).toBe(
      "api/chats?q=Kite+work",
    );
  });

  test("adds a bounded page size when the sidebar requests incremental history", () => {
    expect(chatListRequestUrl("", new Set(["pinned-chat"]), 50)).toBe(
      "api/chats?include=pinned-chat&limit=50",
    );
    expect(chatListRequestUrl("Kite work", [], 900)).toBe("api/chats?q=Kite+work&limit=500");
  });
});

describe("sidebar search performance helpers", () => {
  test("uses a short debounce once trigram search can answer efficiently", () => {
    expect(sidebarSearchDelay("")).toBe(0);
    expect(sidebarSearchDelay("a")).toBe(180);
    expect(sidebarSearchDelay("ab")).toBe(180);
    expect(sidebarSearchDelay("abc")).toBe(70);
    expect(sidebarSearchDelay(" transcript ")).toBe(70);
  });

  test("filters the current sidebar summaries while the server search catches up", () => {
    const chat = {
      title: "Transcript extraction",
      preview: "Keep the SQLite cache fast",
      prompt: "Improve Prompta",
      job_name: "performance",
    };

    expect(sidebarChatMatchesSearch(chat, "transcript")).toBe(true);
    expect(sidebarChatMatchesSearch(chat, "sqlite")).toBe(true);
    expect(sidebarChatMatchesSearch(chat, "PROMPTA")).toBe(true);
    expect(sidebarChatMatchesSearch(chat, "performance")).toBe(true);
    expect(sidebarChatMatchesSearch(chat, "unrelated")).toBe(false);
    expect(sidebarChatMatchesSearch(chat, "   ")).toBe(true);
  });
});

describe("chat refresh focus", () => {
  test("keeps the current conversation selected when newer chats arrive", () => {
    expect(
      selectedConversationAfterChatRefresh("focused-chat", false, [
        { id: "new-chat-2" },
        { id: "new-chat-1" },
      ]),
    ).toBe("focused-chat");
  });

  test("selects the newest chat only when there is no existing focus", () => {
    expect(
      selectedConversationAfterChatRefresh(null, false, [
        { id: "newest-chat" },
        { id: "older-chat" },
      ]),
    ).toBe("newest-chat");
  });

  test("does not select a sidebar chat while composing a new chat", () => {
    expect(
      selectedConversationAfterChatRefresh(null, true, [{ id: "background-chat" }]),
    ).toBeNull();
  });
});

describe("relative time formatting", () => {
  const nowSeconds = 10_000;
  const nowMillis = nowSeconds * 1000;

  test("formats sidebar age labels from an explicit clock tick", () => {
    expect(formatRelativeTime(nowSeconds - 30, nowMillis)).toBe("now");
    expect(formatRelativeTime(nowSeconds - 2 * 60, nowMillis)).toBe("2m");
    expect(formatRelativeTime(nowSeconds - 2 * 60 * 60, nowMillis)).toBe("2h");
  });
});

describe("client send ownership", () => {
  test("matches only client ids created by the current UI session", () => {
    expect(clientIdBelongsToSession("session-a:123-1", "session-a")).toBe(true);
    expect(clientIdBelongsToSession("session-b:123-1", "session-a")).toBe(false);
    expect(clientIdBelongsToSession("legacy-client-id", "session-a")).toBe(false);
    expect(clientIdBelongsToSession("", "session-a")).toBe(false);
  });
});

describe("broken chat detection", () => {
  const now = 10_000;

  test("refreshes sidebar health only when a visible row crosses the broken boundary", () => {
    const rows = [{ id: "live", broken: false }];
    const healthy = [
      {
        id: "live",
        status: "active",
        created_at: 1,
        last_assistant_at: now - 39 * 60,
      },
    ];
    const broken = [
      {
        id: "live",
        status: "active",
        created_at: 1,
        last_assistant_at: now - 40 * 60,
      },
    ];

    expect(sidebarHealthNeedsRefresh(rows, healthy, false, now)).toBe(false);
    expect(sidebarHealthNeedsRefresh(rows, broken, false, now)).toBe(true);
  });

  test("refreshes the sidebar while the broken filter is active so hidden chats can enter", () => {
    expect(sidebarHealthNeedsRefresh([], [], true, now)).toBe(true);
  });

  test("marks an active chat broken at the 40 minute boundary", () => {
    expect(
      chatIsBroken(
        {
          id: "stale",
          status: "active",
          created_at: 1,
          last_assistant_at: now - 40 * 60,
          last_user_at: now - 50 * 60,
        },
        now,
      ),
    ).toBe(true);
  });

  test("keeps a recently responding active chat healthy", () => {
    expect(
      chatIsBroken(
        {
          id: "live",
          status: "active",
          created_at: 1,
          last_assistant_at: now - 39 * 60,
        },
        now,
      ),
    ).toBe(false);
  });

  test("gives a fresh user reply its own 40 minute response window", () => {
    expect(
      chatIsBroken(
        {
          id: "reply",
          status: "active",
          created_at: 1,
          last_assistant_at: now - 3 * 60 * 60,
          last_user_at: now - 5 * 60,
        },
        now,
      ),
    ).toBe(false);
  });

  test("uses message activity timestamps for selected chat details", () => {
    expect(
      chatIsBroken(
        {
          id: "detail",
          status: "interrupted",
          created_at: 1,
          messages: [
            {
              role: "assistant",
              created_at: now - 2 * 60 * 60,
              updated_at: now,
              activity_at: now - 41 * 60,
            },
          ],
        },
        now,
      ),
    ).toBe(true);
  });

  test("never marks completed or optimistic chats broken", () => {
    expect(
      chatIsBroken(
        {
          id: "complete",
          status: "complete",
          created_at: 1,
          last_assistant_at: now - 5 * 60 * 60,
        },
        now,
      ),
    ).toBe(false);
    expect(
      chatIsBroken(
        {
          id: "pending",
          status: "active",
          created_at: 1,
          last_assistant_at: now - 5 * 60 * 60,
          _pending_send: true,
        },
        now,
      ),
    ).toBe(false);
  });
});

describe("sidebar filters", () => {
  const now = 10_000;
  const healthyActive = {
    id: "active",
    status: "active",
    created_at: now - 60,
    last_assistant_at: now - 30,
  };
  const unreadComplete = {
    id: "unread",
    status: "complete",
    created_at: now - 120,
    unread: true,
  };
  const brokenInterrupted = {
    id: "broken",
    status: "interrupted",
    created_at: now - 60 * 60,
    last_assistant_at: now - 41 * 60,
  };

  test("shows every chat when no chips are selected", () => {
    expect(
      sidebarChatMatchesFilters(
        healthyActive,
        { unread: false, active: false, broken: false },
        now,
      ),
    ).toBe(true);
  });

  test("matches unread, active, and broken chips against their existing chat state", () => {
    expect(
      sidebarChatMatchesFilters(
        unreadComplete,
        { unread: true, active: false, broken: false },
        now,
      ),
    ).toBe(true);
    expect(
      sidebarChatMatchesFilters(healthyActive, { unread: false, active: true, broken: false }, now),
    ).toBe(true);
    expect(
      sidebarChatMatchesFilters(
        brokenInterrupted,
        { unread: false, active: false, broken: true },
        now,
      ),
    ).toBe(true);
  });

  test("combines selected chips as an OR filter", () => {
    const filters = { unread: true, active: true, broken: false };

    expect(sidebarChatMatchesFilters(unreadComplete, filters, now)).toBe(true);
    expect(sidebarChatMatchesFilters(healthyActive, filters, now)).toBe(true);
    expect(sidebarChatMatchesFilters(brokenInterrupted, filters, now)).toBe(false);
  });
});

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

describe("deterministic sidebar ordering", () => {
  test("orders pinned first, then every unpinned chat by the latest user message", () => {
    const chats = [
      { id: "revived-old", created_at: 10, last_user_at: 50, updated_at: 5_000 },
      {
        id: "pending-old",
        created_at: 20,
        last_user_at: 20,
        updated_at: 10_000,
        _pending_send: true,
      },
      { id: "newer", created_at: 30, last_user_at: 30, updated_at: 30 },
      { id: "pinned", created_at: 5, last_user_at: 5, updated_at: 5 },
      { id: "optimistic", created_at: 40, last_user_at: 40, _optimisticNew: true },
    ];

    expect(sortSidebarChats(chats, new Set(["pinned"])).map((chat) => chat.id)).toEqual([
      "pinned",
      "revived-old",
      "optimistic",
      "newer",
      "pending-old",
    ]);
  });

  test("read state never changes sidebar position", () => {
    const chats = [
      { id: "pinned", created_at: 5, last_user_at: 5, unread: true },
      { id: "newest", created_at: 30, last_user_at: 30 },
      { id: "middle", created_at: 20, last_user_at: 20, unread: true },
      { id: "oldest", created_at: 10, last_user_at: 10 },
    ];

    const expected = ["pinned", "newest", "middle", "oldest"];
    expect(sortSidebarChats(chats, new Set(["pinned"])).map((chat) => chat.id)).toEqual(expected);

    for (const chat of chats) chat.unread = !chat.unread;

    expect(sortSidebarChats(chats, new Set(["pinned"])).map((chat) => chat.id)).toEqual(expected);
  });

  test("keeps pinned chats in pin insertion order with new pins at the end", () => {
    const chats = [
      { id: "third-pin", created_at: 300 },
      { id: "first-pin", created_at: 100 },
      { id: "second-pin", created_at: 200 },
      { id: "unpinned", created_at: 400 },
    ];

    expect(
      sortSidebarChats(chats, new Set(["first-pin", "second-pin", "third-pin"])).map(
        (chat) => chat.id,
      ),
    ).toEqual(["first-pin", "second-pin", "third-pin", "unpinned"]);
  });

  test("assistant or status activity never changes ordinary chat position", () => {
    const chats = [
      { id: "newer-user-message", created_at: 30, last_user_at: 30, updated_at: 30 },
      { id: "older-user-message", created_at: 10, last_user_at: 10, updated_at: 10_000 },
    ];

    expect(sortSidebarChats(chats, new Set()).map((chat) => chat.id)).toEqual([
      "newer-user-message",
      "older-user-message",
    ]);
  });

  test("falls back to thread creation time only when no user-message timestamp exists", () => {
    expect(sidebarChatLastUserAt({ id: "chat", created_at: 123, last_user_at: 456 })).toBe(456);
    expect(sidebarChatLastUserAt({ id: "legacy", created_at: 123 })).toBe(123);
    expect(sidebarChatCreatedAt({ id: "chat", created_at: 123, last_user_at: 456 } as any)).toBe(
      123,
    );
  });

  test("recognizes every sidebar pending representation", () => {
    expect(sidebarChatIsPending({ id: "server", _pending_send: true })).toBe(true);
    expect(sidebarChatIsPending({ id: "new", _optimisticNew: true })).toBe(true);
    expect(sidebarChatIsPending({ id: "reply", _optimisticReply: true })).toBe(true);
    expect(sidebarChatIsPending({ id: "done" })).toBe(false);
  });

  test("pending sends do not claim a conversation is complete before ChatGPT replies", () => {
    expect(pendingConversationStatus("complete", "queued")).toBe("pending");
    expect(pendingConversationStatus("complete", "succeeded")).toBe("pending");
    expect(pendingConversationStatus("", "queued")).toBe("pending");
    expect(pendingConversationStatus("", "running")).toBe("pending");
    expect(pendingConversationStatus("active", "succeeded")).toBe("active");
    expect(pendingConversationStatus("complete", "failed")).toBe("failed");
  });

  test("keeps the pending new chat selected after the server assigns its conversation id", () => {
    expect(
      sidebarChatIsSelected(
        { id: "pending-new-client-1", _optimisticNew: true },
        null,
        true,
        "pending-new-client-1",
      ),
    ).toBe(true);
    expect(
      sidebarChatIsSelected(
        { id: "WEB:real-chat", _pending_send: true },
        null,
        true,
        "WEB:real-chat",
      ),
    ).toBe(true);
    expect(
      sidebarChatIsSelected(
        { id: "WEB:other-chat", _pending_send: true },
        null,
        true,
        "WEB:real-chat",
      ),
    ).toBe(false);
  });

  test("pending new-chat selection takes precedence over the previous durable selection", () => {
    expect(sidebarSelectedConversationId("WEB:previous-chat", true, "pending-new-client-1")).toBe(
      "pending-new-client-1",
    );
    expect(
      sidebarChatIsSelected(
        { id: "WEB:previous-chat" },
        "WEB:previous-chat",
        true,
        "pending-new-client-1",
      ),
    ).toBe(false);
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

  test("matches the server pending row by client id even for duplicate prompts", () => {
    const matched = matchingOptimisticConversation(
      [
        {
          id: "pending-new-other",
          prompt: "same prompt",
          created_at: 1_000,
          _pending_send: true,
          _client_id: "other-client",
        },
        {
          id: "pending-new-target",
          prompt: "same prompt",
          created_at: 1_000,
          _pending_send: true,
          _client_id: "target-client",
        },
      ],
      { clientId: "target-client", message: "same prompt", createdAt: 1_000 },
    );

    expect(matched?.id).toBe("pending-new-target");
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
      [{ id: "WEB:real-chat", prompt: "server prompt", created_at: 500 }],
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
      [{ id: "WEB:unknown-age", prompt: "fix the sidebar" }],
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

describe("pending sidebar conversations", () => {
  test("keeps a succeeded new chat visible until the durable chat list adopts it", () => {
    const pending = new Map([
      [
        "WEB:new-chat",
        [
          {
            clientId: "client-1",
            sendId: "send-1",
            conversationId: "WEB:new-chat",
            message: "keep this visible",
            status: "succeeded",
            createdAt: 1_000,
            updatedAt: 1_005,
          },
        ],
      ],
    ]);

    expect(missingPendingConversationSummaries([{ id: "WEB:other-chat" }], pending)).toEqual([
      expect.objectContaining({
        id: "WEB:new-chat",
        status: "active",
        title: "keep this visible",
        preview: "keep this visible",
      }),
    ]);
  });

  test("stops synthesizing a pending row once the server chat list contains it", () => {
    const pending = new Map([
      [
        "WEB:new-chat",
        [
          {
            conversationId: "WEB:new-chat",
            message: "keep this visible",
            status: "succeeded",
            updatedAt: 1_005,
          },
        ],
      ],
    ]);

    expect(missingPendingConversationSummaries([{ id: "WEB:new-chat" }], pending)).toEqual([]);
  });

  test("applies sidebar search to synthetic pending rows", () => {
    const pending = new Map([
      [
        "WEB:new-chat",
        [
          {
            conversationId: "WEB:new-chat",
            message: "fix sidebar persistence",
            status: "running",
            updatedAt: 1_005,
          },
        ],
      ],
    ]);

    expect(missingPendingConversationSummaries([], pending, "sidebar")).toHaveLength(1);
    expect(missingPendingConversationSummaries([], pending, "unrelated")).toEqual([]);
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
    expect(shouldRenderNewChatView(false, fingerprint, "older")).toBe(true);
  });
});

describe("pending chat pin promotion", () => {
  test("uses the optimistic pending id before ChatGPT assigns a conversation id", () => {
    expect(
      pendingConversationDisplayId({
        clientId: "client-1",
        conversationId: "",
      }),
    ).toBe("pending-new-client-1");
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
  test("keeps unresolved pending ids in the pending-new view", () => {
    expect(
      isUnresolvedPendingNewConversation(
        { clientId: "client-1", conversationId: "", status: "queued" },
        "pending-new-client-1",
      ),
    ).toBe(true);
    expect(
      isUnresolvedPendingNewConversation(
        { clientId: "client-1", conversationId: "WEB:new-chat", status: "running" },
        "WEB:new-chat",
      ),
    ).toBe(true);
  });

  test("lets a succeeded pending chat resolve to the real conversation route", () => {
    expect(
      isUnresolvedPendingNewConversation(
        { clientId: "client-1", conversationId: "WEB:new-chat", status: "succeeded" },
        "WEB:new-chat",
      ),
    ).toBe(false);
    expect(
      isUnresolvedPendingNewConversation(
        { clientId: "client-1", conversationId: "", status: "failed" },
        "WEB:other-chat",
      ),
    ).toBe(false);
  });

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

describe("slash command keyboard navigation", () => {
  test("moves through visible commands and wraps at either end", () => {
    expect(nextSlashCommandIndex(4, -1, 1)).toBe(0);
    expect(nextSlashCommandIndex(4, -1, -1)).toBe(3);
    expect(nextSlashCommandIndex(4, 0, -1)).toBe(3);
    expect(nextSlashCommandIndex(4, 3, 1)).toBe(0);
    expect(nextSlashCommandIndex(4, 1, 1)).toBe(2);
  });

  test("returns no selection when there are no visible commands", () => {
    expect(nextSlashCommandIndex(0, 0, 1)).toBe(-1);
  });
});

describe("message timestamps", () => {
  test("formats clock times explicitly in 12-hour am/pm form", () => {
    expect(formatClockTime12Hour(new Date(2026, 8, 22, 0, 5, 9), true)).toBe("12:05:09am");
    expect(formatClockTime12Hour(new Date(2026, 8, 22, 13, 7, 0))).toBe("1:07pm");
    expect(formatDailyTime12Hour("00:05")).toBe("12:05am");
    expect(formatDailyTime12Hour("13:07")).toBe("1:07pm");
  });

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
    expect(pendingSendActivity("queued", true, 0, 0, undefined, 3)).toEqual({
      label: "queued · #3",
      statusText: "Queued in Prompta · #3",
    });
    expect(pendingSendActivity("queued", true, 0, 0, 1_000, 3, 1_900)).toEqual({
      label: "queued · #3 · ETA ~15m",
      statusText: "Queued in Prompta · #3 · ETA ~15m",
    });
    expect(pendingSendActivity("queued", true, 0, 0, 1_000, 20, 10_000)).toEqual({
      label: "queued · #20 · ETA ~2h 30m",
      statusText: "Queued in Prompta · #20 · ETA ~2h 30m",
    });
    expect(pendingSendActivity("running", true)).toEqual({
      label: "sending",
      statusText: "Sending to ChatGPT…",
    });
  });

  test("shows rate-limit backoff without turning the send into a failure", () => {
    expect(pendingSendActivity("rate_limited", true, 300)).toEqual({
      label: "rate limited · retry in 5m",
      statusText: "Rate limited — backing off; retrying automatically in 5m.",
    });
    expect(pendingSendActivity("rate_limited", true, 300, 1_300, 1_000, 2, 1_900)).toEqual({
      label: "rate limited · #2 · ETA ~15m · retry in 5m",
      statusText:
        "Queued in Prompta · #2 · ETA ~15m. Rate limited — backing off; retrying automatically in 5m.",
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

  test("keeps waiting after send acceptance only when result polling is enabled", () => {
    expect(pendingSendActivity("succeeded", true)).toEqual({
      label: "waiting",
      statusText: "Waiting for ChatGPT…",
    });
    expect(pendingSendActivity("succeeded", true, 0, 0, undefined, 0, 0, false)).toBeNull();
  });

  test("shows transient retry backoff and stops on terminal queue failures", () => {
    expect(pendingSendActivity("retrying", true, 4, 1_004, 1_000)).toEqual({
      label: "retrying · <1m",
      statusText: "Send failed transiently — retrying automatically in <1m.",
    });
    expect(pendingSendActivity("retrying", true, 120, 1_120, 1_000, 3, 1_900)).toEqual({
      label: "retrying · #3 · ETA ~15m · 2m",
      statusText:
        "Queued in Prompta · #3 · ETA ~15m. Send failed transiently — retrying automatically in 2m.",
    });
    expect(pendingSendActivity("failed", true)).toBeNull();
    expect(pendingSendActivity("dead_lettered", true)).toBeNull();
    expect(pendingSendActivity("outcome_unknown", true)).toBeNull();
  });
});

describe("POST request recovery", () => {
  test("times out a stalled request instead of hanging forever", async () => {
    const stalledFetch = ((_: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      })) as typeof fetch;

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

  test("marks exhausted network fetch failures as transport failures", async () => {
    const offlineFetch = (async () => {
      throw new TypeError("network unavailable");
    }) as typeof fetch;
    let caught: unknown;

    try {
      await postJsonRequest("api/chats", { message: "hello" }, 1, 1_000, offlineFetch);
    } catch (error) {
      caught = error;
    }

    expect(isPostJsonTransportError(caught)).toBe(true);
    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toBe("network unavailable");
  });

  test("does not classify server HTTP failures as offline transport failures", async () => {
    const serverFailureFetch = (async () =>
      new Response(JSON.stringify({ error: "server failed" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      })) as typeof fetch;
    let caught: unknown;

    try {
      await postJsonRequest("api/chats", { message: "hello" }, 1, 1_000, serverFailureFetch);
    } catch (error) {
      caught = error;
    }

    expect(isPostJsonTransportError(caught)).toBe(false);
    expect((caught as Error).message).toBe("server failed");
  });

  test("rejects malformed JSON from a successful response", async () => {
    const malformedFetch = (async () =>
      new Response("not json", {
        status: 202,
        headers: { "Content-Type": "application/json" },
      })) as typeof fetch;

    await expect(
      postJsonRequest("api/chats", { message: "hello" }, 1, 1_000, malformedFetch),
    ).rejects.toThrow("Prompta returned an invalid response");
  });
});

describe("DELETE request recovery", () => {
  test("times out a stalled delete instead of hiding a still-running send", async () => {
    const stalledFetch = ((_: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      })) as typeof fetch;

    await expect(deleteRequest("api/sends/send-1", 10, stalledFetch)).rejects.toThrow(
      "Request timed out",
    );
  });

  test("treats an already-missing send as successfully deleted", async () => {
    const missingFetch = (async (_: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe("DELETE");
      expect(init?.signal).toBeInstanceOf(AbortSignal);

      return new Response("", { status: 404 });
    }) as typeof fetch;

    await expect(deleteRequest("api/sends/send-1", 1_000, missingFetch)).resolves.toBeUndefined();
  });

  test("keeps server delete failures visible to the caller", async () => {
    const failingFetch = (async () =>
      new Response("", {
        status: 500,
        statusText: "Internal Server Error",
      })) as typeof fetch;

    await expect(deleteRequest("api/sends/send-1", 1_000, failingFetch)).rejects.toThrow(
      "500 Internal Server Error",
    );
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

  test("reconciles the first new-chat message without relying on cache timestamps", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "start a fresh chat",
          created_at: 9_000,
        },
        {
          role: "assistant",
          content: "First reply",
          created_at: 9_001,
        },
      ],
      {
        message: "start a fresh chat",
        origin: "new",
        createdAt: 1_000,
        updatedAt: 4_000,
      },
    );

    expect(matchedIndex).toBe(0);
  });

  test("matches a delayed durable reply against the latest pending update time", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 4_002,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
        updatedAt: 4_000,
      },
    );

    expect(matchedIndex).toBe(0);
  });

  test("matches a durable reply first observed long after the send", () => {
    const matchedIndex = matchingPendingReplyMessageIndex(
      [
        {
          role: "user",
          content: "keep fixing bugs",
          created_at: 1_180,
        },
      ],
      {
        message: "keep fixing bugs",
        createdAt: 1_000,
        updatedAt: 1_005,
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

describe("selected chat refresh", () => {
  const summary = { status: "complete", updated_at: 123 };

  test("forces a server detail refresh after cached startup hydration", () => {
    expect(shouldRefreshSelectedChat(summary, 123, "cached-fingerprint", true)).toBe(true);
  });

  test("can reuse an unchanged selected detail after the startup refresh", () => {
    expect(shouldRefreshSelectedChat(summary, 123, "server-fingerprint")).toBe(false);
  });

  test("refreshes when status or timestamp says the cached detail may be stale", () => {
    expect(
      shouldRefreshSelectedChat({ status: "active", updated_at: 123 }, 123, "fingerprint"),
    ).toBe(true);
    expect(shouldRefreshSelectedChat(summary, 122, "fingerprint")).toBe(true);
    expect(shouldRefreshSelectedChat(summary, 123, "")).toBe(true);
  });
});

describe("historical activity probing", () => {
  test("refreshes interrupted or unattended chats because their cached state may advance", () => {
    expect(shouldProbeHistoricalActivity("interrupted")).toBe(true);
    expect(shouldProbeHistoricalActivity("unattended")).toBe(true);
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
      runAtLabel: `${new Date(2026, 8, 21, 9, 30, 0).toLocaleDateString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
      })} 9:30am`,
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
    expect(sidebarPreviewText("Fixed ```tool:Open tool call list Open tool call list ```")).toBe(
      "Fixed",
    );
  });

  test("removes multiline tool fences and normalizes whitespace", () => {
    expect(sidebarPreviewText('Before  ```tool-call: shell\n{"cmd":"true"}\n```  after')).toBe(
      "Before after",
    );
  });
});

test("falls back to the original prompt when the latest message is tool-only", () => {
  expect(
    sidebarChatPreviewText(
      '```tool:Nox Python MCP · execute_python\n{"arguments":{}}\n```',
      "Fix the chat sidebar preview",
    ),
  ).toBe("Fix the chat sidebar preview");
});

test("prefers real assistant prose over the original prompt", () => {
  expect(
    sidebarChatPreviewText("Working on it ```tool:Shell\n{}\n```", "Fix the chat sidebar preview"),
  ).toBe("Working on it");
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
    expect(
      toolCallSummary(
        JSON.stringify({
          summary: "Inspecting Tool Call Ordering in ChatGPT DOM",
          arguments: { pageId: 5 },
        }),
      ),
    ).toBe("Inspecting Tool Call Ordering in ChatGPT DOM");
    expect(toolCallSummary(JSON.stringify({ arguments: { pageId: 5 } }))).toBe("");
  });

  test("extracts tool call timestamps in seconds or milliseconds", () => {
    expect(toolCallTimestampMillis(JSON.stringify({ created_at: 1_700_000_000 }))).toBe(
      1_700_000_000_000,
    );
    expect(toolCallTimestampMillis(JSON.stringify({ timestamp: 1_700_000_000_123 }))).toBe(
      1_700_000_000_123,
    );
    expect(toolCallTimestampMillis(JSON.stringify({ created_at: 1e30 }))).toBeNull();
    expect(toolCallTimestampMillis(JSON.stringify({ arguments: { pageId: 5 } }))).toBeNull();
  });

  test("extracts only Python source from Nox and Glass MCP tool payloads", () => {
    const nox = JSON.stringify({
      arguments: {
        code: "from pathlib import Path\nprint(Path.cwd())",
        cwd: "/home/example/prompta",
      },
      status: "completed",
      result: { stdout: "/home/example/prompta\n" },
    });
    const glass = JSON.stringify({
      arguments: JSON.stringify({
        code: "import socket\nprint(socket.gethostname())",
        timeout_seconds: 120,
      }),
      status: "completed",
    });

    expect(pythonToolCallCode("Nox Python MCP · execute_python", nox)).toBe(
      "from pathlib import Path\nprint(Path.cwd())",
    );
    expect(pythonToolCallCode("Glass · execute_python", glass)).toBe(
      "import socket\nprint(socket.gethostname())",
    );
  });

  test("strips leading blank lines from Python MCP code for display only", () => {
    const payload = JSON.stringify({
      arguments: {
        code: "\n \t\n  print('keeps indentation')\n",
      },
    });

    expect(pythonToolCallCode("Nox Python MCP · execute_python", payload)).toBe(
      "  print('keeps indentation')\n",
    );
  });

  test("does not reinterpret non-Python MCP JSON as Python", () => {
    expect(
      pythonToolCallCode(
        "GitHub · get_issue",
        JSON.stringify({ arguments: { code: "not python" } }),
      ),
    ).toBe("");
  });
});

describe("ChatGPT rich-text markers", () => {
  const start = "\uE200";
  const end = "\uE201";
  const sep = "\uE202";

  test("turns native URL markers into renderer-controlled links", () => {
    const input = `Deployed ${start}url${sep}Commit e5612bc${sep}https://github.com/example/prompta/commit/e5612bc${end}.`;
    expect(replaceChatGptRichMarkers(input, (label, url) => `<a href="${url}">${label}</a>`)).toBe(
      'Deployed <a href="https://github.com/example/prompta/commit/e5612bc">Commit e5612bc</a>.',
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
