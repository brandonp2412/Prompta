import { expect, test } from "bun:test";
import { createJobsPageController } from "../src/ui/JobsPageController";
import { createChatsPageController } from "../src/ui/ChatsPageController";

const snapshot = (position: number) => ({
  max_workers: 1,
  occupied_slots: 1,
  estimated_run_seconds: 120,
  estimate_samples: 5,
  waiting: [
    {
      name: "scheduled",
      position,
      reason: "global",
      occupied: 1,
      limit: 1,
      eta_seconds: position * 120,
    },
  ],
});

test("overlapping queue refreshes apply the newest response last", async () => {
  const original = globalThis.fetch;
  let releaseFirst: ((response: Response) => void) | undefined;
  let calls = 0;
  globalThis.fetch = (async () => {
    calls += 1;
    if (calls === 1)
      return new Promise<Response>((resolve) => {
        releaseFirst = resolve;
      });
    return Response.json(snapshot(1));
  }) as typeof fetch;
  try {
    const model = createJobsPageController({});
    const first = model.loadQueue();
    await model.loadQueue();
    expect(calls).toBe(1);
    releaseFirst?.(Response.json(snapshot(3)));
    await first;
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls).toBe(2);
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});

test("malformed successful queue responses do not crash job rendering", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    Response.json({ ...snapshot(2), waiting: [{ name: 42, position: "bad" }] })) as typeof fetch;
  try {
    const model = createJobsPageController({});
    await model.loadQueue();
    expect(model.queueSnapshot.value).toBeNull();
    expect(model.queueSnapshot.value?.waiting).toBeUndefined();
    expect(model.queueError.value).toContain("temporarily unavailable");
  } finally {
    globalThis.fetch = original;
  }
});

test("Chats labels the last confirmed queue position as stale during an outage", async () => {
  const original = globalThis.fetch;
  let response = Response.json(snapshot(2));
  globalThis.fetch = (async () => response) as typeof fetch;
  try {
    const model = createChatsPageController({
      view: "chats",
      selectedRunId: null,
      newChatOpen: false,
      onSelect: () => {},
      onNavigate: () => {},
      onNewChat: () => {},
      onQueued: () => {},
    });
    await model.loadQueue();
    expect(model.visibleWaiting.value[0]?.position).toBe(2);
    response = new Response("Temporary gateway error", { status: 500 });
    await model.loadQueue();
    expect(model.visibleWaiting.value[0]?.position).toBe(2);
    expect(model.queueError.value).toContain("Showing the last confirmed positions and ETAs");
    response = Response.json(snapshot(1));
    await model.loadQueue();
    expect(model.visibleWaiting.value[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});

test("an unavailable queue estimate clears its old position and recovers", async () => {
  const original = globalThis.fetch;
  let response = Response.json(snapshot(2));
  globalThis.fetch = (async () => response) as typeof fetch;
  try {
    const model = createJobsPageController({});
    await model.loadQueue();
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(2);

    response = new Response("unavailable", { status: 500 });
    await model.loadQueue();
    expect(model.queueSnapshot.value).toBeNull();
    expect(model.queueError.value).toContain("temporarily unavailable");

    response = Response.json(snapshot(1));
    await model.loadQueue();
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});
