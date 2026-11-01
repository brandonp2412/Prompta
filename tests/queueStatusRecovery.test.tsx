import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "bun:test";
import { createJobsPageController } from "../src/ui/JobsPageController";
import { createChatsPageController } from "../src/ui/ChatsPageController";

import JobsTable from "../src/ui/JobsTable";
import ChatsSidebar from "../src/ui/ChatsSidebar";

afterEach(cleanup);
function jobsView() {
  const model = createJobsPageController({});
  model.jobs.value = [
    {
      images: [],
      name: "scheduled",
      created_order: 0,
      prompt: "Question",
      status: "healthy",
      status_message: "",
      paused: false,
      run_at_epoch: null,
      pin_chat: false,
      daily_at: null,
      interval_minutes: 60,
      exact_interval: false,
      source_revision: "",
      next_due_at_epoch: 0,
      last_sent_at: 0,
      last_uncertain_send_at: 0,
    },
  ];
  render(<JobsTable model={model} />);
  return model;
}
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
  globalThis.fetch = Object.assign(
    async () => {
      calls += 1;
      if (calls === 1)
        return new Promise<Response>((resolve) => {
          releaseFirst = resolve;
        });
      return Response.json(snapshot(1));
    },
    { preconnect: original.preconnect },
  );
  try {
    const model = jobsView();
    const first = model.loadQueue();
    await act(async () => {
      await model.loadQueue();
    });
    expect(calls).toBe(1);
    await act(async () => {
      releaseFirst?.(Response.json(snapshot(3)));
      await first;
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(calls).toBe(2);
    expect(screen.getByText(/Queue #1 of 1/)).toBeTruthy();
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});

test("malformed successful queue responses do not crash job rendering", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = Object.assign(
    async () => Response.json({ ...snapshot(2), waiting: [{ name: 42, position: "bad" }] }),
    { preconnect: original.preconnect },
  );
  try {
    const model = jobsView();
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.queueSnapshot.value).toBeNull();
    expect(screen.queryByText(/Queue #/)).toBeNull();
    expect(model.queueError.value).toContain("temporarily unavailable");
  } finally {
    globalThis.fetch = original;
  }
});

test("Chats labels the last confirmed queue position as stale during an outage", async () => {
  const original = globalThis.fetch;
  let response = Response.json(snapshot(2));
  globalThis.fetch = Object.assign(async () => response, { preconnect: original.preconnect });
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
    render(
      <ChatsSidebar
        model={model}
        refs={{ sidebarPane: () => {}, searchInput: () => {}, listPane: () => {} }}
      />,
    );
    await act(async () => {
      await model.loadQueue();
    });
    expect(screen.getByText("#2 of 1")).toBeTruthy();
    expect(model.visibleWaiting.value[0]?.position).toBe(2);
    response = new Response("Temporary gateway error", { status: 500 });
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.visibleWaiting.value[0]?.position).toBe(2);
    expect(model.queueError.value).toContain("Showing the last confirmed positions and ETAs");
    expect(document.querySelector(".recovery-error")).toBeNull();
    expect(screen.getByText("#2 of 1")).toBeTruthy();
    response = Response.json(snapshot(1));
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.visibleWaiting.value[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});

test("an unavailable queue estimate clears its old position and recovers", async () => {
  const original = globalThis.fetch;
  let response = Response.json(snapshot(2));
  globalThis.fetch = Object.assign(async () => response, { preconnect: original.preconnect });
  try {
    const model = jobsView();
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(2);

    response = new Response("unavailable", { status: 500 });
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.queueSnapshot.value).toBeNull();
    expect(model.queueError.value).toContain("temporarily unavailable");

    response = Response.json(snapshot(1));
    await act(async () => {
      await model.loadQueue();
    });
    expect(model.queueSnapshot.value?.waiting[0]?.position).toBe(1);
    expect(model.queueError.value).toBe("");
  } finally {
    globalThis.fetch = original;
  }
});
