import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatComposer from "../src/ui/ChatComposer";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function fallbackProps() {
  const submitted: string[] = [];
  return {
    submitted,
    props: {
      mode: "reply" as const,
      chatId: crypto.randomUUID(),
      onSend: async () => ({
        ok: false,
        message: "Exact branch unavailable",
        fallbackAvailable: true,
      }),
      onFallbackSend: async (text: string) => {
        submitted.push(text);
        return { ok: true, message: "New chat queued." };
      },
      onNewChat: () => {},
    },
  };
}

test("explicit fallback remains usable while exact sending is paused", async () => {
  const user = userEvent.setup();
  const { props, submitted } = fallbackProps();
  const view = render(<ChatComposer {...props} />);
  await user.type(screen.getByRole("textbox"), "Continue with this answer");
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  await screen.findByRole("button", { name: "Continue in new chat" });
  view.rerender(<ChatComposer {...props} sendDisabled />);
  await user.click(screen.getByRole("button", { name: "Continue in new chat" }));
  await waitFor(() => expect(submitted).toEqual(["Continue with this answer"]));
  expect(screen.getByRole("textbox").textContent).toBe("");
  await screen.findByText("New chat queued.");
});

test("globally disabled composer preserves the draft and blocks fallback", async () => {
  const user = userEvent.setup();
  const { props, submitted } = fallbackProps();
  const view = render(<ChatComposer {...props} />);
  await user.type(screen.getByRole("textbox"), "Keep this draft");
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  await screen.findByRole("button", { name: "Continue in new chat" });
  view.rerender(<ChatComposer {...props} disabled />);
  const fallback = screen.getByRole("button", { name: "Continue in new chat" });
  expect(fallback.hasAttribute("disabled")).toBe(true);
  await user.click(fallback);
  expect(submitted).toEqual([]);
  expect(screen.getByDisplayValue("Keep this draft")).toBeTruthy();
});

test("switching from reply to new chat focuses the desktop textbox and removes stale fallback", async () => {
  const user = userEvent.setup();
  const { props, submitted } = fallbackProps();
  const view = render(<ChatComposer {...props} />);
  await user.type(screen.getByRole("textbox"), "Preserved text");
  await user.click(screen.getByRole("button", { name: "Send reply" }));
  await screen.findByRole("button", { name: "Continue in new chat" });
  view.rerender(<ChatComposer {...props} mode="fresh" chatId={undefined} />);
  expect(screen.queryByRole("button", { name: "Continue in new chat" })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole("textbox"));
  expect(submitted).toEqual([]);
});
