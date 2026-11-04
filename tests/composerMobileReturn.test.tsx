import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";

const originalMatchMedia = window.matchMedia.bind(window);

function useMobileKeyboard() {
  window.matchMedia = (query) => {
    const result = originalMatchMedia(query);
    return query === "(pointer: coarse)"
      ? new Proxy(result, {
          get(target, property) {
            return property === "matches" ? true : Reflect.get(target, property, target);
          },
        })
      : result;
  };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  window.matchMedia = originalMatchMedia;
});

test("mobile Return adds a newline and only Send submits the multiline reply", async () => {
  useMobileKeyboard();
  const user = userEvent.setup();
  const sent: string[] = [];
  render(
    <ChatComposer
      mode="reply"
      chatId={crypto.randomUUID()}
      onSend={async (text) => {
        sent.push(text);
        return { ok: true, message: "Queued" };
      }}
      onNewChat={() => {}}
    />,
  );
  const field = screen.getByRole("textbox") as HTMLTextAreaElement;
  expect(field.getAttribute("enterkeyhint")).toBe("enter");
  await user.type(field, "First line{Enter}Second line");
  expect(field.value).toBe("First line\nSecond line");
  expect(sent).toEqual([]);
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  expect(sent).toEqual(["First line\nSecond line"]);
});

test("mobile Return also keeps a fresh chat as a multiline draft", async () => {
  useMobileKeyboard();
  const user = userEvent.setup();
  const sent: string[] = [];
  render(
    <ChatComposer
      mode="fresh"
      onSend={async (text) => {
        sent.push(text);
        return { ok: true, message: "Created" };
      }}
      onNewChat={() => {}}
    />,
  );
  const field = screen.getByRole("textbox") as HTMLTextAreaElement;
  await user.type(field, "New chat{Enter}More details");
  expect(field.value).toBe("New chat\nMore details");
  expect(sent).toEqual([]);
  await user.click(screen.getByRole("button", { name: /Send/ }));
  expect(sent).toEqual(["New chat\nMore details"]);
});

test("mobile Return does not execute slash commands or choose mention autocomplete", async () => {
  useMobileKeyboard();
  const user = userEvent.setup();
  const commands: string[] = [];
  const sent: string[] = [];
  render(
    <ChatComposer
      mode="reply"
      chatId={crypto.randomUUID()}
      onSend={async (text) => {
        sent.push(text);
        return { ok: true, message: "Queued" };
      }}
      onCommand={(command) => {
        commands.push(command);
      }}
      onNewChat={() => {}}
    />,
  );
  const field = screen.getByRole("textbox") as HTMLTextAreaElement;
  await user.type(field, "/jobs{Enter}");
  expect(field.value).toBe("/jobs\n");
  expect(commands).toEqual([]);
  await user.clear(field);
  await user.type(field, "Ask @gla{Enter}");
  expect(field.value).toBe("Ask @gla\n");
  expect(sent).toEqual([]);
  expect(commands).toEqual([]);
});
