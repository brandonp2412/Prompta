import React from "react";
import { afterEach, expect, test } from "bun:test";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatTranscript from "../src/ui/ChatTranscript";
import { createChatsPageController } from "../src/ui/ChatsPageController";

afterEach(cleanup);

test("an interrupted reply can be stopped after the live composer Stop disappears", async () => {
  const model = createChatsPageController({
    view: "chats", selectedRunId: "interrupted", newChatOpen: false,
    onSelect: () => {}, onNavigate: () => {}, onNewChat: () => {}, onQueued: () => {},
  });
  model.detail.value = {
    send_id: "interrupted", job_name: "", title: "Interrupted chat", preview: "", status: "completed",
    has_response: true, last_reply_revision: "", last_read_revision: "", last_reply_at: 0,
    created_at: 1, updated_at: 1, finished_at: 2, user_text: "Original", assistant_text: "Answer",
    source: "dom", accepted_at: 1, images: [], manual_recovery_pending: 1,
  };
  model.turns.value = [{ reply_id: "reply", user_text: "Follow up", assistant_text: "", status: "interrupted", created_at: 3, updated_at: 4 }];
  const stopped: string[] = [];
  model.stopJob = async (id) => { stopped.push(id); };
  render(<ChatTranscript model={model} refs={{ scrollPane: () => {} }} conversationUrl="https://chatgpt.com/c/12345678-1234-4123-8123-123456789abc" />);
  expect(screen.getByRole("button", { name: "Recovery queued" }).hasAttribute("disabled")).toBe(true);
  await userEvent.setup().click(screen.getByRole("button", { name: "Stop recovery" }));
  expect(stopped).toEqual(["interrupted"]);
  act(() => { model.turns.value = model.turns.value.map((turn) => ({ ...turn, status: "stopped" })); });
  expect(screen.queryByRole("button", { name: "Stop recovery" })).toBeNull();
});
