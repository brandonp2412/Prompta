import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";
import type { SlashCommandId } from "../src/ui/slashCommands";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function setup() {
  const commands: SlashCommandId[] = [];
  const sent: string[] = [];
  const chatId = crypto.randomUUID();
  render(
    <ChatComposer
      mode="reply"
      chatId={chatId}
      onSend={async (text) => {
        sent.push(text);
        return { ok: true, message: "Queued" };
      }}
      onNewChat={() => {}}
      onCommand={(command) => {
        commands.push(command);
      }}
    />,
  );
  return { commands, sent };
}

test("typing a slash shows commands, Enter runs one without sending a chat", async () => {
  const user = userEvent.setup();
  const { commands, sent } = setup();
  const field = screen.getByRole("textbox");
  await user.type(field, "/jobs");
  expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeTruthy();
  expect(screen.getByRole("option", { name: /\/jobs/ })).toBeTruthy();
  await user.keyboard("{Enter}");
  expect(commands).toEqual(["jobs"]);
  expect(sent).toEqual([]);
  expect((field as HTMLTextAreaElement).value).toBe("");
});

test("aliases, arrow selection and Tab work", async () => {
  const user = userEvent.setup();
  const { commands } = setup();
  const field = screen.getByRole("textbox");
  await user.type(field, "/q{Tab}");
  expect(commands).toEqual(["jobs"]);
  await user.type(field, "/");
  await user.keyboard("{ArrowDown}{Enter}");
  expect(commands).toEqual(["jobs", "chats"]);
});

test("Escape dismisses, unknown commands are blocked, regular text still sends", async () => {
  const user = userEvent.setup();
  const { commands, sent } = setup();
  const field = screen.getByRole("textbox");
  await user.type(field, "/unknown");
  await user.keyboard("{Enter}");
  expect(commands).toEqual([]);
  expect(sent).toEqual([]);
  await user.clear(field);
  await user.type(field, "/new");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox", { name: "Slash commands" })).toBeNull();
  await user.keyboard("{Enter}");
  expect(commands).toEqual(["new"]);
  await user.type(field, "/jobs with context{Enter}");
  expect(sent).toEqual(["/jobs with context"]);
});

test("help opens full picker and clear only erases the composer", async () => {
  const user = userEvent.setup();
  const { commands, sent } = setup();
  const field = screen.getByRole("textbox");
  await user.type(field, "/help{Enter}");
  expect((field as HTMLTextAreaElement).value).toBe("/");
  expect(screen.getAllByRole("option").length).toBeGreaterThanOrEqual(10);
  await user.clear(field);
  await user.type(field, "/clear{Enter}");
  expect((field as HTMLTextAreaElement).value).toBe("");
  expect(commands).toEqual([]);
  expect(sent).toEqual([]);
});
