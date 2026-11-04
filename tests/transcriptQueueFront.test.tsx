import React from "react";
import { afterEach, expect, test } from "bun:test";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import ChatTranscript from "../src/ui/ChatTranscript";
import ChatsSidebar from "../src/ui/ChatsSidebar";
import { createChatsPageController } from "../src/ui/ChatsPageController";

afterEach(cleanup);

test("bump control appears by the queued transcript response, never in the sidebar", () => {
  const model = createChatsPageController({
    view: "chats", selectedRunId: "waiting", newChatOpen: false,
    onSelect: () => {}, onNavigate: () => {}, onNewChat: () => {}, onQueued: () => {},
  });
  const detail = {
    send_id: "waiting", job_name: "", title: "Waiting chat", preview: "", status: "queued" as const,
    has_response: false, last_reply_revision: "", last_read_revision: "", last_reply_at: 0,
    created_at: 1, updated_at: 1, finished_at: 0, user_text: "My question", assistant_text: "",
    source: "", accepted_at: 0, images: [],
  };
  model.detail.value = detail;
  model.items.value = [detail];
  model.turns.value = [{ reply_id: "", user_text: detail.user_text, assistant_text: "", status: "queued", created_at: 1, updated_at: 1 }];
  model.queueSnapshot.value = {
    max_workers: 1, occupied_slots: 1, estimated_run_seconds: 600, estimate_samples: 0,
    waiting: [{ name: "Scheduled job", one_time: false, position: 1, reason: "global", occupied: 1, limit: 1, eta_seconds: 600 }],
    waiting_runs: [{ send_id: "waiting", eta_seconds: 600 }],
  };
  render(<>
    <ChatsSidebar model={model} refs={{ sidebarPane: () => {}, searchInput: () => {}, listPane: () => {} }} />
    <ChatTranscript model={model} refs={{ scrollPane: () => {} }} conversationUrl={null} />
  </>);
  expect(within(screen.getByLabelText("Assistant response 1")).getByRole("button", { name: "Bump Waiting chat to front of queue" })).toBeTruthy();
  expect(within(screen.getByLabelText("Local chat sidebar")).queryByRole("button", { name: /to front of queue/ })).toBeNull();
  act(() => { model.queueSnapshot.value = { ...model.queueSnapshot.value, waiting_runs: [] }; });
  expect(screen.queryByRole("button", { name: /to front of queue/ })).toBeNull();
});

test("queued follow-up no longer claims it is waiting for a completed response", () => {
  const model = createChatsPageController({
    view: "chats", selectedRunId: "finished", newChatOpen: false,
    onSelect: () => {}, onNavigate: () => {}, onNewChat: () => {}, onQueued: () => {},
  });
  model.detail.value = {
    send_id: "finished", job_name: "", title: "Finished chat", preview: "", status: "queued",
    has_response: true, last_reply_revision: "", last_read_revision: "", last_reply_at: 0,
    created_at: 1, updated_at: 2, finished_at: 2, user_text: "Original question",
    assistant_text: "Original answer", source: "history_dom", accepted_at: 1, images: [],
  };
  model.turns.value = [
    { reply_id: "", user_text: "Original question", assistant_text: "Original answer",
      status: "completed", message_id: "original-message", created_at: 1, updated_at: 2 },
    { reply_id: "next", user_text: "Follow-up question", assistant_text: "",
      status: "prepared", queued_by_user: true, created_at: 3, updated_at: 3 },
  ];
  render(<ChatTranscript model={model} refs={{ scrollPane: () => {} }} conversationUrl={null} />);
  expect(screen.getByText("Follow-up queued · waiting for dispatch")).toBeTruthy();
  expect(screen.queryByText("Follow-up queued · waiting for the preceding response")).toBeNull();
});
