import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";
import {
  activeMention,
  insertMention,
  selectedDraftMentions,
  suggestedMentions,
} from "../src/ui/composerMentions";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function setup() {
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
  return sent;
}

test("recognizes @ at the caret, not in email addresses, and preserves surrounding text", () => {
  expect(activeMention("ping me@example.com", 19)).toBeNull();
  expect(activeMention("Try @g later", 6)).toEqual({ start: 4, end: 6, query: "g" });
  expect(activeMention("@", 1)).toEqual({ start: 0, end: 1, query: "" });
  expect(insertMention("Try @g later", { start: 4, end: 6, query: "g" }, "Glass")).toEqual({
    value: "Try @Glass  later",
    cursor: 11,
  });
  expect(suggestedMentions("patch")).toHaveLength(1);
  expect(suggestedMentions("patch")[0].name).toBe("Patchright Brave");
});

test("selected indicator extraction handles multiple and multi-word mentions without email false positives", () => {
  const text = "Ask @Glass Serena and @Patchright Brave, not me@example.com or @Glassworks";
  expect(selectedDraftMentions(text).map(({ mention }) => mention.name)).toEqual([
    "Glass Serena",
    "Patchright Brave",
  ]);
});

test("autocomplete chooses connector with Enter, then Enter sends the draft", async () => {
  const user = userEvent.setup();
  const sent = setup();
  const input = screen.getByRole("textbox");
  await user.type(input, "Ask @gla");
  expect(screen.getByRole("listbox", { name: "Tools and connectors" })).toBeTruthy();
  expect(screen.getByRole("option", { name: /Glass Develop/ })).toBeTruthy();
  await user.keyboard("{Enter}");
  expect(sent).toEqual([]);
  expect((input as HTMLTextAreaElement).value).toBe("Ask @Glass ");
  expect(screen.getByRole("button", { name: "Remove @Glass" })).toBeTruthy();
  expect(screen.queryByRole("listbox")).toBeNull();
  await user.type(input, "to check logs{Enter}");
  expect(sent).toEqual(["Ask @Glass to check logs"]);
  expect(screen.queryByRole("button", { name: "Remove @Glass" })).toBeNull();
});

test("removing an indicator removes only that mention and keeps the draft editable", async () => {
  const user = userEvent.setup();
  const sent = setup();
  const input = screen.getByRole("textbox");
  await user.type(input, "Ask @gla{Enter}and @matrix{Enter}for help");
  expect(screen.getByRole("button", { name: "Remove @Glass" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Remove @Matrix" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Remove @Glass" }));
  expect((input as HTMLTextAreaElement).value).toBe("Ask and @Matrix for help");
  expect(screen.queryByRole("button", { name: "Remove @Glass" })).toBeNull();
  expect(screen.getByRole("button", { name: "Remove @Matrix" })).toBeTruthy();
  await user.keyboard("{End}{Enter}");
  expect(sent).toEqual(["Ask and @Matrix for help"]);
});

test("arrow keys navigate autocomplete without moving the caret or sending", async () => {
  const user = userEvent.setup();
  setup();
  const input = screen.getByRole("textbox");
  await user.type(input, "@gla");
  await user.keyboard("{ArrowDown}{Enter}");
  expect((input as HTMLTextAreaElement).value).toBe("@Glass Serena ");
});

test("Tab and click select tools; Escape dismisses without sending", async () => {
  const user = userEvent.setup();
  setup();
  const input = screen.getByRole("textbox");
  await user.type(input, "@web");
  await user.keyboard("{Tab}");
  expect((input as HTMLTextAreaElement).value).toBe("@Web search ");
  await user.type(input, "@ma");
  expect(screen.getByRole("option", { name: /Matrix Read/ })).toBeTruthy();
  await user.click(screen.getByRole("option", { name: /Matrix Read/ }));
  expect((input as HTMLTextAreaElement).value).toBe("@Web search @Matrix ");
  await user.type(input, "@glass");
  expect(screen.getByRole("listbox")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
});
