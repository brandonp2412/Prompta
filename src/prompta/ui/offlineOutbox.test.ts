import { describe, expect, test } from "bun:test";

import { createOfflinePostRecord, OfflineOutbox, type OfflinePostRecord } from "./offlineOutbox";

describe("offline post records", () => {
  test("captures enough data to safely retry a failed reply", () => {
    const record = createOfflinePostRecord(
      "/tenant-a",
      {
        operation: "reply",
        targetChatId: " chat-42 ",
        message: "send this later",
        attachments: [
          {
            name: "chart.png",
            type: "image/png",
            data: "data:image/png;base64,abc",
          },
        ],
        clientId: "client-session:send-1",
        lastError: "network unavailable",
      },
      1_795_000_000_000,
    );

    expect(record).toEqual({
      id: "/tenant-a:client-session:send-1",
      scope: "/tenant-a",
      operation: "reply",
      targetChatId: "chat-42",
      message: "send this later",
      attachments: [
        {
          name: "chart.png",
          type: "image/png",
          data: "data:image/png;base64,abc",
        },
      ],
      clientId: "client-session:send-1",
      createdAt: 1_795_000_000_000,
      retryState: "pending",
      retryCount: 0,
      lastAttemptAt: null,
      lastError: "network unavailable",
    });
  });

  test("uses the client id as the stable per-scope outbox key", () => {
    const first = createOfflinePostRecord(
      "/tenant-a",
      {
        operation: "new_chat",
        message: "hello",
        clientId: "session:1",
      },
      100,
    );
    const retry = createOfflinePostRecord(
      "/tenant-a",
      {
        operation: "new_chat",
        message: "hello",
        clientId: "session:1",
      },
      200,
    );

    expect(first.id).toBe(retry.id);
    expect(first.targetChatId).toBeNull();
  });

  test("enqueue writes the prepared record through the persistence boundary", async () => {
    const writes: OfflinePostRecord[] = [];
    const outbox = new OfflineOutbox("/tenant-a", {
      put: async (record) => {
        writes.push(record);
      },
    });

    const record = await outbox.enqueue({
      operation: "reply",
      targetChatId: "chat-7",
      message: "queued offline",
      clientId: "session:7",
      lastError: "Request timed out",
    });

    expect(writes).toHaveLength(1);
    expect(writes[0]).toEqual(record);
    expect(record.retryState).toBe("pending");
    expect(record.retryCount).toBe(0);
  });

  test("rejects records without an idempotency id", () => {
    expect(() =>
      createOfflinePostRecord("/tenant-a", {
        operation: "new_chat",
        message: "hello",
        clientId: "   ",
      }),
    ).toThrow("Offline outbox requires a client id");
  });
});
