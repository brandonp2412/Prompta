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

test("loads 100 chats and fetches older chats only after clicking Load more", async () => {
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
  fireEvent.scroll(pane, { target: { scrollTop: 10000 } });
  expect(requests).toHaveLength(1);
  await userEvent.setup().click(screen.getByRole("button", { name: "Load more chats" }));
  await screen.findByText("Chat 101");
  expect(requests[1]?.searchParams.get("offset")).toBe("100");
  await waitFor(() => expect(screen.queryByRole("button", { name: "Load more chats" })).toBeNull());
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

test("running chats have no Stop button in the sidebar", async () => {
  const { model } = sidebar();
  await act(async () => {
    model.items.value = [{ ...run(7), status: "generating", has_response: false }];
  });
  expect(screen.getByText("Chat 7")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
});
