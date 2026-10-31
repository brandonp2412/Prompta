import { expect, test } from "bun:test";
import { acknowledgeFreshQueueRequest, freshQueueRequest } from "../src/ui/freshQueueReceipt";
import {
  acknowledgeExactReplyRequest,
  pendingExactReplyRequest,
  pendingQueuedFollowupRequest,
} from "../src/ui/pendingExactReply";

const freshKey = "prompta.pending-fresh-requests.v1";
const replyKey = "prompta.pending-exact-replies.v1";

async function withStorage(
  storage: {
    getItem: (key: string) => string | null;
    setItem: (key: string, value: string) => void;
  },
  action: () => Promise<void>,
) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
  try {
    await action();
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
}

test("fresh and exact sends fail closed when browser receipt reads are blocked", async () => {
  await withStorage(
    {
      getItem: () => {
        throw new Error("Denied");
      },
      setItem: () => {
        throw new Error("Denied");
      },
    },
    async () => {
      await expect(freshQueueRequest("Secret " + crypto.randomUUID(), [])).rejects.toThrow(
        "cannot be read from browser storage",
      );
      await expect(
        pendingExactReplyRequest("send", "conversation", "parent", crypto.randomUUID()),
      ).rejects.toThrow("cannot be read from browser storage");
    },
  );
});

test("fresh and exact sends reject apparent writes that are not retained", async () => {
  await withStorage(
    {
      getItem: () => null,
      setItem: () => {},
    },
    async () => {
      await expect(freshQueueRequest("Secret " + crypto.randomUUID(), [])).rejects.toThrow(
        "cannot be saved in browser storage",
      );
      await expect(
        pendingExactReplyRequest("send", "conversation", "parent", crypto.randomUUID()),
      ).rejects.toThrow("cannot be saved in browser storage");
    },
  );
});

test("confirmed sends survive a later storage cleanup failure without another POST", async () => {
  const stored = new Map<string, string>();
  let writable = true;
  await withStorage(
    {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => {
        if (!writable) throw new Error("Quota exceeded");
        stored.set(key, value);
      },
    },
    async () => {
      const prompt = "Send " + crypto.randomUUID();
      const reply = "Reply " + crypto.randomUUID();
      const fresh = await freshQueueRequest(prompt, []);
      const exact = await pendingExactReplyRequest("send", "conversation", "parent", reply);
      writable = false;
      acknowledgeFreshQueueRequest(fresh.fingerprint, fresh.requestId);
      acknowledgeExactReplyRequest(exact.fingerprint, exact.replyId);
      expect(stored.get(freshKey)).toContain(fresh.requestId);
      expect(stored.get(replyKey)).toContain(exact.replyId);
      expect((await freshQueueRequest(prompt, [])).requestId).toBe(fresh.requestId);
      expect(
        (await pendingExactReplyRequest("send", "conversation", "parent", reply)).replyId,
      ).toBe(exact.replyId);
    },
  );
});

test("a malformed legacy follow-up ID cannot silently generate a new send ID", async () => {
  const stored = new Map<string, string>();
  const sendId = "legacy-" + crypto.randomUUID();
  stored.set("prompta.pending-followup.v1." + sendId, "{");
  await withStorage(
    {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => {
        stored.set(key, value);
      },
    },
    async () => {
      await expect(pendingQueuedFollowupRequest(sendId, "A follow-up")).rejects.toThrow(
        "legacy browser storage",
      );
      expect(stored.has(replyKey)).toBe(false);
    },
  );
});

test("conflicting duplicate fingerprints fail closed instead of selecting a random ID", async () => {
  const stored = new Map<string, string>();
  await withStorage(
    {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => {
        stored.set(key, value);
      },
    },
    async () => {
      const prompt = "Duplicate " + crypto.randomUUID();
      const fresh = await freshQueueRequest(prompt, []);
      const existing = JSON.parse(stored.get(freshKey) || "[]") as Record<string, unknown>[];
      stored.set(
        freshKey,
        JSON.stringify([...existing, { ...existing[0], requestId: "a".repeat(32) }]),
      );
      await expect(freshQueueRequest(prompt, [])).rejects.toThrow("unreadable");

      const reply = "Duplicate " + crypto.randomUUID();
      const exact = await pendingExactReplyRequest("send", "conversation", "parent", reply);
      const entries = JSON.parse(stored.get(replyKey) || "[]") as Record<string, unknown>[];
      stored.set(
        replyKey,
        JSON.stringify([...entries, { ...entries[0], replyId: "b".repeat(32) }]),
      );
      await expect(
        pendingExactReplyRequest("send", "conversation", "parent", reply),
      ).rejects.toThrow("unreadable");
      expect(fresh.requestId).not.toBe("");
      expect(exact.replyId).not.toBe("");
    },
  );
});
