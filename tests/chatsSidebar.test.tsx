import React from "react";
import { afterEach, expect, test } from "bun:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatsSidebar from "../src/ui/ChatsSidebar";
import { createChatsPageController } from "../src/ui/ChatsPageController";
import type { RunSummary } from "../src/ui/resultFormatting";

const originalFetch = globalThis.fetch;
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});
const run = (index: number): RunSummary => ({
  send_id: String(index),
  job_name: "",
  title: `Chat ${index}`,
  preview: "Answer",
  status: "completed",
  has_response: true,
  last_reply_revision: "",
  last_read_revision: "",
  last_reply_at: index,
  created_at: index,
  updated_at: index,
  finished_at: index,
});
function sidebar() {
  const model = createChatsPageController({
    view: "chats",
    selectedRunId: null,
    newChatOpen: false,
    onSelect: () => {},
    onNavigate: () => {},
    onNewChat: () => {},
    onQueued: () => {},
  });
  const view = render(
    <ChatsSidebar
      model={model}
      refs={{
        sidebarPane: () => {},
        searchInput: () => {},
        listPane: (element) => {
          model.listPane.value = element ?? undefined;
        },
      }}
    />,
  );
  return { model, view };
}

test("loads older chats as the reader approaches the end of the sidebar", async () => {
  const requests: URL[] = [];
  globalThis.fetch = Object.assign(
    async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      requests.push(url);
      const offset = Number(url.searchParams.get("offset"));
      return Response.json({
        items: offset ? [run(101)] : Array.from({ length: 100 }, (_, i) => run(i)),
        total: 101,
      });
    },
    { preconnect: originalFetch.preconnect },
  );
  const { model } = sidebar();
  await act(async () => {
    await model.loadList(true);
  });
  expect(requests).toHaveLength(1);
  expect(requests[0]?.searchParams.get("limit")).toBe("100");
  const pane = document.querySelector(".chats-list");
  if (!pane) throw new Error("Chat list missing");
  expect(screen.queryByRole("button", { name: "Load more chats" })).toBeNull();
  fireEvent.scroll(pane, { target: { scrollTop: 10000 } });
  await screen.findByText("Chat 101");
  expect(requests[1]?.searchParams.get("offset")).toBe("100");
  expect(requests).toHaveLength(2);
});

test("sidebar search responds within a short typing pause and cancels obsolete requests", async () => {
  const queries: string[] = [];
  let firstAborted = false;
  globalThis.fetch = Object.assign(
    (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = new URL(String(input), "http://localhost");
      const query = url.searchParams.get("q") ?? "";
      queries.push(query);
      if (query === "first") {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => {
              firstAborted = true;
              reject(new DOMException("Superseded", "AbortError"));
            },
            { once: true },
          );
        });
      }
      return Promise.resolve(Response.json({ items: [run(query === "second" ? 2 : 1)], total: 1 }));
    },
    { preconnect: originalFetch.preconnect },
  );
  const { model } = sidebar();
  await act(async () => {
    model.items.value = [run(0)];
  });
  fireEvent.click(screen.getByRole("button", { name: "Search chats" }));
  const search = screen.getByRole("searchbox", { name: "Search chats" });
  fireEvent.change(search, { target: { value: "first" } });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 220));
  });
  expect(queries).toEqual(["first"]);
  fireEvent.change(search, { target: { value: "second" } });
  await waitFor(() => expect(queries).toEqual(["first", "second"]));
  await waitFor(() => expect(screen.getByText("Chat 2")).toBeTruthy());
  expect(firstAborted).toBe(true);
  expect(screen.queryByText("Chat 1")).toBeNull();
  expect(model.nextOffset.value).toBe(1);
});

test("a failed older-chat page stops auto-retries and provides a manual retry", async () => {
  let failOlderPage = true;
  let olderPageRequests = 0;
  globalThis.fetch = Object.assign(
    async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (Number(url.searchParams.get("offset")) === 100) {
        olderPageRequests++;
        if (failOlderPage) return new Response("Unavailable", { status: 500 });
        return Response.json({ items: [run(101)], total: 101 });
      }
      return Response.json({ items: Array.from({ length: 100 }, (_, i) => run(i)), total: 101 });
    },
    { preconnect: originalFetch.preconnect },
  );
  const { model } = sidebar();
  await act(async () => {
    await model.loadList(true);
  });
  const pane = document.querySelector(".chats-list");
  if (!pane) throw new Error("Chat list missing");
  fireEvent.scroll(pane, { target: { scrollTop: 10000 } });
  const retry = await screen.findByRole("button", { name: "Retry loading older chats" });
  await act(async () => {
    await model.loadList(); // A live refresh must not restart failed infinite scrolling.
  });
  fireEvent.scroll(pane, { target: { scrollTop: 10000 } });
  expect(olderPageRequests).toBe(1);
  failOlderPage = false;
  await userEvent.setup().click(retry);
  await screen.findByText("Chat 101");
  expect(olderPageRequests).toBe(2);
  expect(screen.queryByRole("button", { name: "Retry loading older chats" })).toBeNull();
});

test("new pins appear after existing pins and unpinning preserves remaining order", async () => {
  const { model } = sidebar();
  globalThis.fetch = Object.assign(async () => Response.json({ items: model.pinned.peek() }), {
    preconnect: originalFetch.preconnect,
  });
  await act(async () => {
    model.items.value = [run(1), run(2), run(3)];
    model.pinsReady.value = true;
    await model.togglePin(run(1));
    await model.togglePin(run(2));
    await model.togglePin(run(3));
  });
  expect(model.pinnedIds.value).toEqual(["1", "2", "3"]);
  const titles = () =>
    Array.from(document.querySelectorAll(".chat-row-top strong"), (element) => element.textContent);
  expect(titles()).toEqual(["Chat 1", "Chat 2", "Chat 3"]);
  await userEvent.setup().click(screen.getByRole("button", { name: "Unpin Chat 2" }));
  await waitFor(() => expect(model.pinnedIds.value).toEqual(["1", "3"]));
  expect(titles().slice(0, 2)).toEqual(["Chat 1", "Chat 3"]);
});

test("fresh chats enter their final pinned position without a second jump", async () => {
  const { model } = sidebar();
  let acceptedId = "";
  let finishPins: ((response: Response) => void) | undefined;
  globalThis.fetch = Object.assign(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/api/chats") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as { request_id: string };
        acceptedId = "manual-" + payload.request_id;
        return Response.json({ send_id: acceptedId, status: "queued" }, { status: 202 });
      }
      if (url.pathname.endsWith("/api/results"))
        return Response.json({
          items: [{ ...run(3), send_id: acceptedId }, run(2), run(1)],
          total: 3,
        });
      if (url.pathname.endsWith("/api/local-chat-pins"))
        return new Promise((resolve) => {
          finishPins = resolve;
        });
      throw new Error("Unexpected URL: " + url.pathname);
    },
    { preconnect: originalFetch.preconnect },
  );
  await act(async () => {
    model.items.value = [run(2), run(1)];
    model.pinnedIds.value = ["1"];
    model.pinsReady.value = true;
  });

  await act(async () => {
    expect((await model.sendFresh("New chat insertion regression", [])).ok).toBe(true);
  });
  const fresh = await screen.findByText("Chat 3");
  const row = fresh.closest(".chat-entry");
  expect(row?.classList.contains("arriving")).toBe(true);
  const titles = () =>
    Array.from(document.querySelectorAll(".chat-row-top strong"), (element) => element.textContent);
  expect(titles()).toEqual(["Chat 1", "Chat 3", "Chat 2"]);
  expect(model.pinnedIds.value).toEqual(["1", acceptedId]);

  await act(async () => {
    finishPins?.(Response.json({ items: [run(1), { ...run(3), send_id: acceptedId }] }));
  });
  expect(titles()).toEqual(["Chat 1", "Chat 3", "Chat 2"]);
  expect(fresh.closest(".chat-entry")).toBe(row);
  fireEvent.animationEnd(row!);
  expect(row?.classList.contains("arriving")).toBe(false);
});

test("running chats have no Stop button in the sidebar", async () => {
  const { model } = sidebar();
  await act(async () => {
    model.items.value = [{ ...run(7), status: "generating", has_response: false }];
  });
  expect(screen.getByText("Chat 7")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
});

test("queued follow-ups show their ETA instead of a stale answer preview", async () => {
  const { model } = sidebar();
  await act(async () => {
    model.queueSnapshot.value = {
      ...model.queueSnapshot.peek(),
      waiting_runs: [{ send_id: "7", eta_seconds: 120 }],
    };
    model.items.value = [{ ...run(7), status: "queued", preview: "Older completed answer" }];
  });
  expect(screen.getByText("Queued · ETA ~2 min")).toBeTruthy();
  expect(screen.queryByText("Older completed answer")).toBeNull();

  await act(async () => {
    model.items.value = [{ ...run(7), status: "accepted", preview: "Older completed answer" }];
  });
  expect(document.querySelector(".chat-row-meta")?.textContent).toBe("Accepted");
  expect(screen.queryByText("Older completed answer")).toBeNull();

  await act(async () => {
    model.items.value = [{ ...run(7), status: "completed", preview: "New completed answer" }];
  });
  expect(screen.getByText("New completed answer")).toBeTruthy();
});

test("sidebar shows queued once jobs but hides repeating scheduled deliveries", async () => {
  const { model } = sidebar();
  await act(async () => {
    model.queueSnapshot.value = {
      max_workers: 1,
      occupied_slots: 1,
      estimated_run_seconds: 120,
      estimate_samples: 5,
      waiting: [
        {
          name: "recurring",
          one_time: false,
          position: 1,
          reason: "global",
          occupied: 1,
          limit: 1,
          eta_seconds: 120,
        },
        {
          name: "due-once",
          one_time: true,
          position: 2,
          reason: "global",
          occupied: 1,
          limit: 1,
          eta_seconds: 240,
        },
      ],
    };
    model.items.value = [
      { ...run(1), title: "Repeating job", job_name: "recurring", status: "queued" },
      { ...run(2), title: "Due once chat", job_name: "due-once", status: "queued" },
      { ...run(3), title: "Manual once chat", status: "queued" },
    ];
  });
  expect(model.visibleWaiting.value.map((job) => job.name)).toEqual(["due-once"]);
  expect(screen.getByText("due-once")).toBeTruthy();
  expect(screen.getByText("#2 of 2")).toBeTruthy();
  expect(screen.getByText("Manual once chat")).toBeTruthy();
  expect(screen.queryByText("Repeating job")).toBeNull();
  expect(screen.queryByText("recurring")).toBeNull();
  expect(screen.queryByText("Due once chat")).toBeNull();
});

test("settings cannot be saved before a successful load", async () => {
  let resolveSettings: ((response: Response) => void) | undefined;
  const saves: unknown[] = [];
  globalThis.fetch = Object.assign(
    (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      if (init?.method === "PUT") {
        saves.push(JSON.parse(String(init.body)));
        return Promise.resolve(Response.json({}));
      }
      return new Promise<Response>((resolve) => {
        resolveSettings = resolve;
      });
    },
    { preconnect: originalFetch.preconnect },
  );
  sidebar();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Profile" }));
  await user.click(screen.getByRole("button", { name: "Settings" }));
  const save = screen.getByRole("button", { name: "Save settings" }) as HTMLButtonElement;
  const limit = screen.getByRole("checkbox", {
    name: "Limit concurrent jobs and chats",
  }) as HTMLInputElement;
  const workers = screen.getByRole("spinbutton", { name: "Maximum workers" }) as HTMLInputElement;
  const approval = screen.getByRole("checkbox", {
    name: "Automatically approve trusted connector prompts",
  }) as HTMLInputElement;
  expect(save.disabled).toBe(true);
  expect(limit.disabled).toBe(true);
  expect(workers.disabled).toBe(true);
  expect(approval.disabled).toBe(true);
  await user.click(save);
  expect(saves).toEqual([]);

  await act(async () => {
    resolveSettings?.(
      Response.json({
        parallelism: { enabled: true, max_workers: 7 },
        connector_approval: { enabled: true },
      }),
    );
  });
  await waitFor(() => expect(save.disabled).toBe(false));
  expect(limit.disabled).toBe(false);
  expect(workers.disabled).toBe(false);
  expect(approval.disabled).toBe(false);
  expect(
    (screen.getByRole("spinbutton", { name: "Maximum workers" }) as HTMLInputElement).value,
  ).toBe("7");
  await user.click(save);
  await waitFor(() => expect(saves).toHaveLength(1));
  expect(saves[0]).toEqual({
    parallelism: { enabled: true, max_workers: 7 },
    connector_approval: { enabled: true },
  });
});

test("a failed settings load can be retried without closing the dialog", async () => {
  let loads = 0;
  let saves = 0;
  globalThis.fetch = Object.assign(
    async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") {
        saves++;
        return Response.json({});
      }
      loads++;
      if (loads === 1) return new Response("Unavailable", { status: 503 });
      return Response.json({
        parallelism: { enabled: true, max_workers: 3 },
        connector_approval: { enabled: false },
      });
    },
    { preconnect: originalFetch.preconnect },
  );
  sidebar();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Profile" }));
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await screen.findByRole("alert");
  const retry = screen.getByRole("button", { name: "Retry loading settings" });
  expect((retry as HTMLButtonElement).disabled).toBe(false);
  expect(
    (screen.getByRole("checkbox", { name: "Limit concurrent jobs and chats" }) as HTMLInputElement)
      .disabled,
  ).toBe(true);
  await user.click(retry);
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "Save settings" }) as HTMLButtonElement).disabled,
    ).toBe(false),
  );
  expect(loads).toBe(2);
  expect(screen.queryByRole("alert")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  expect(saves).toBe(1);
});

test("malformed settings stay disabled and allow a safe retry", async () => {
  let loads = 0;
  globalThis.fetch = Object.assign(
    async () => {
      loads++;
      if (loads === 1) return Response.json({ parallelism: null });
      return Response.json({
        parallelism: { enabled: false, max_workers: 2 },
        connector_approval: { enabled: true },
      });
    },
    { preconnect: originalFetch.preconnect },
  );
  sidebar();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Profile" }));
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Retry loading settings" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Retry loading settings" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save settings" })).toBeTruthy());
  expect(loads).toBe(2);
  expect(
    (screen.getByRole("spinbutton", { name: "Maximum workers" }) as HTMLInputElement).value,
  ).toBe("2");
});

test("a server-confirmed read clears a stale optimistic unread badge", async () => {
  globalThis.fetch = Object.assign(async () => Response.json({}), {
    preconnect: originalFetch.preconnect,
  });
  const { model } = sidebar();
  const initial = { ...run(7), last_reply_revision: "revision-one" };
  await act(async () => {
    model.items.value = [initial];
  });
  expect(document.querySelector(".unread-indicator")).not.toBeNull();

  // This tab optimistically marks revision one read.
  await act(async () => {
    model.selectRun(initial);
  });
  expect(document.querySelector(".unread-indicator")).toBeNull();

  // Another tab has since read revision two. The old optimistic revision
  // must not make the authoritative, fully-read server row look unread.
  await act(async () => {
    model.items.value = [
      { ...initial, last_reply_revision: "revision-two", last_read_revision: "revision-two" },
    ];
  });
  expect(document.querySelector(".unread-indicator")).toBeNull();

  // A genuinely newer response must still be flagged as unread.
  await act(async () => {
    model.items.value = [
      { ...initial, last_reply_revision: "revision-three", last_read_revision: "revision-two" },
    ];
  });
  expect(document.querySelector(".unread-indicator")).not.toBeNull();
});

test("maximum workers can be cleared and replaced without submitting an invalid value", async () => {
  const saves: unknown[] = [];
  globalThis.fetch = Object.assign(
    async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") {
        saves.push(JSON.parse(String(init.body)));
        return Response.json({});
      }
      return Response.json({
        parallelism: { enabled: true, max_workers: 3 },
        connector_approval: { enabled: false },
      });
    },
    { preconnect: originalFetch.preconnect },
  );
  sidebar();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Profile" }));
  await user.click(screen.getByRole("button", { name: "Settings" }));
  const workers = (await screen.findByRole("spinbutton", {
    name: "Maximum workers",
  })) as HTMLInputElement;
  const save = screen.getByRole("button", { name: "Save settings" }) as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));

  await user.clear(workers);
  expect(workers.value).toBe("");
  expect(save.disabled).toBe(true);
  await user.type(workers, "12");
  expect(workers.value).toBe("12");
  expect(save.disabled).toBe(false);
  await user.click(save);
  expect(saves).toEqual([
    {
      parallelism: { enabled: true, max_workers: 12 },
      connector_approval: { enabled: false },
    },
  ]);
});
