import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

test("running chat shows Stop in the composer; typing swaps it to Send and clearing restores Stop", async () => {
  const user = userEvent.setup();
  const stopped: string[] = [];
  const sent: string[] = [];
  const props = {
    mode: "reply" as const,
    chatId: crypto.randomUUID(),
    active: true,
    onStop: () => { stopped.push("stop"); },
    onSend: async (value: string) => {
      sent.push(value);
      return { ok: true, message: "Queued." };
    },
    onNewChat: () => {},
  };
  render(<ChatComposer {...props} />);
  expect(screen.getByRole("button", { name: "Stop generating" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "New chat" })).toBeNull();

  await user.type(screen.getByRole("textbox"), "Queue a follow-up");
  expect(screen.queryByRole("button", { name: "Stop generating" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  expect(sent).toEqual(["Queue a follow-up"]);
  expect(stopped).toEqual([]);
  expect(screen.getByRole("button", { name: "Stop generating" })).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Stop generating" }));
  expect(stopped).toEqual(["stop"]);
});

test("Enter stops an active empty chat, but submitting drafted text sends it", async () => {
  const user = userEvent.setup();
  let stops = 0;
  const sends: string[] = [];
  render(<ChatComposer
    mode="reply"
    chatId={crypto.randomUUID()}
    active
    onStop={() => { stops += 1; }}
    onSend={async (text) => {
      sends.push(text);
      return { ok: true, message: "Queued" };
    }}
    onNewChat={() => {}}
  />);
  await user.type(screen.getByRole("textbox"), "{Enter}");
  expect(stops).toBe(1);
  expect(sends).toEqual([]);

  await user.type(screen.getByRole("textbox"), "Send this{Enter}");
  expect(sends).toEqual(["Send this"]);
  expect(stops).toBe(1);
});

test("Stop follows the viewed chat state and the active cancellation target", async () => {
  const user = userEvent.setup();
  const stopped: string[] = [];
  const props = (chatId: string, active: boolean) => ({
    mode: "reply" as const,
    chatId,
    active,
    onStop: () => { stopped.push(chatId); },
    onSend: async () => ({ ok: true, message: "" }),
    onNewChat: () => {},
  });
  const view = render(<ChatComposer {...props("a", true)} />);
  view.rerender(<ChatComposer {...props("b", false)} />);
  expect(screen.queryByRole("button", { name: "Stop generating" })).toBeNull();
  expect(screen.getByRole("button", { name: "New chat" })).toBeTruthy();
  view.rerender(<ChatComposer {...props("b", true)} />);
  await user.click(screen.getByRole("button", { name: "Stop generating" }));
  expect(stopped).toEqual(["b"]);
  view.rerender(<ChatComposer {...props("b", true)} stopping />);
  expect(screen.getByRole("button", { name: "Stopping chat" }).hasAttribute("disabled")).toBe(true);
});
