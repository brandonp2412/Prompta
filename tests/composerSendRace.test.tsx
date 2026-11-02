import React from "react";
import { afterEach, expect, test } from "bun:test";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";
import {
  clearComposerDraft,
  readComposerDraft,
  rememberComposerDraft,
} from "../src/ui/composerDraftMemory";

afterEach(() => {
  cleanup();
  localStorage.clear();
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((finish) => {
    resolve = finish;
  });
  return { promise, resolve };
}

test("late acknowledgment cannot unlock or clear another chat composer", async () => {
  const user = userEvent.setup();
  const first = deferred<{ ok: boolean; message: string }>();
  const second = deferred<{ ok: boolean; message: string }>();
  const keyA = "prompta.reply-draft.v1.race-chat-A";
  const keyB = "prompta.reply-draft.v1.race-chat-B";
  rememberComposerDraft(keyA, "First message");
  rememberComposerDraft(keyB, "Second message");
  const props = (chatId: string) => ({
    mode: "reply" as const,
    chatId,
    onSend: () => (chatId === "race-chat-A" ? first.promise : second.promise),
    onNewChat: () => {},
  });
  const view = render(<ChatComposer {...props("race-chat-A")} />);
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  view.rerender(<ChatComposer {...props("race-chat-B")} />);
  expect(screen.getByDisplayValue("Second message")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  await act(async () => {
    first.resolve({ ok: true, message: "" });
    await first.promise;
  });
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
  expect(screen.queryByRole("button", { name: "Sending" })).toBeNull();
  expect(screen.getByRole("button", { name: "New chat" })).toBeTruthy();
  expect(readComposerDraft(keyA)).toBeUndefined();
  await act(async () => {
    second.resolve({ ok: true, message: "" });
    await second.promise;
  });
  expect(screen.getByRole("button", { name: "New chat" })).toBeTruthy();
  expect(readComposerDraft(keyB)).toBeUndefined();
  clearComposerDraft(keyA);
  clearComposerDraft(keyB);
});

for (const replacement of ["Newer draft", "Same words"]) {
  test(`revisiting a chat preserves a newer edit: ${replacement}`, async () => {
    const user = userEvent.setup();
    const chatId = crypto.randomUUID();
    const key = "prompta.reply-draft.v1." + chatId;
    const pending = deferred<{ ok: boolean; message: string }>();
    rememberComposerDraft(key, "Same words");
    const props = {
      mode: "reply" as const,
      chatId,
      onSend: () => pending.promise,
      onNewChat: () => {},
    };
    const view = render(<ChatComposer {...props} />);
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    view.rerender(<ChatComposer {...props} chatId="other-chat" />);
    view.rerender(<ChatComposer {...props} />);
    await user.clear(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), replacement);
    await act(async () => {
      pending.resolve({ ok: true, message: "" });
      await pending.promise;
    });
    expect(screen.getByDisplayValue(replacement)).toBeTruthy();
    expect(readComposerDraft(key)).toBe(replacement);
    clearComposerDraft(key);
  });
}

test("reply clears immediately and accepts another draft without a send spinner", async () => {
  const user = userEvent.setup();
  const receipt = deferred<{ ok: boolean; message: string }>();
  const messages: string[] = [];
  const chatId = crypto.randomUUID();
  const key = "prompta.reply-draft.v1." + chatId;
  const view = render(
    <ChatComposer
      mode="reply"
      chatId={chatId}
      onSend={(text) => {
        messages.push(text);
        return receipt.promise;
      }}
      onNewChat={() => {}}
    />,
  );
  const field = screen.getByRole("textbox", { name: "Message for current chat" });
  await user.type(field, "Revive this chat");
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  expect(messages).toEqual(["Revive this chat"]);
  expect((field as HTMLTextAreaElement).value).toBe("");
  expect(screen.queryByRole("button", { name: "Sending" })).toBeNull();
  await user.type(field, "Another thought");
  expect(screen.getByRole("button", { name: "Send reply" })).toBeTruthy();
  await act(async () => {
    receipt.resolve({ ok: true, message: "" });
    await receipt.promise;
  });
  expect((field as HTMLTextAreaElement).value).toBe("Another thought");
  expect(readComposerDraft(key)).toBe("Another thought");
  view.unmount();
  clearComposerDraft(key);
});

test("failed reply queue receipt restores text alongside a newer draft", async () => {
  const user = userEvent.setup();
  const receipt = deferred<{ ok: boolean; message: string }>();
  const chatId = crypto.randomUUID();
  const key = "prompta.reply-draft.v1." + chatId;
  const view = render(
    <ChatComposer
      mode="reply"
      chatId={chatId}
      onSend={() => receipt.promise}
      onNewChat={() => {}}
    />,
  );
  const field = screen.getByRole("textbox", { name: "Message for current chat" });
  await user.type(field, "Unqueued message");
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  await user.type(field, "New draft");
  await act(async () => {
    receipt.resolve({ ok: false, message: "Queue unavailable" });
    await receipt.promise;
  });
  expect((field as HTMLTextAreaElement).value).toBe("Unqueued message\n\nNew draft");
  expect(readComposerDraft(key)).toBe("Unqueued message\n\nNew draft");
  view.unmount();
  clearComposerDraft(key);
});
