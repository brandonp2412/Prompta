import React from "react";
import { afterEach, expect, test } from "bun:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import QueueFrontButton from "../src/ui/QueueFrontButton";

const originalFetch = globalThis.fetch;
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

test("bumps the existing queue item and refreshes its position", async () => {
  const calls: string[] = [];
  let refreshed = false;
  globalThis.fetch = Object.assign(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push(String(input));
    expect(init?.method).toBe("POST");
    return Response.json({ ok: true });
  }, { preconnect: originalFetch.preconnect });
  render(<QueueFrontButton endpoint="./api/queue/send-2/front" label="Second chat" onMoved={async () => { refreshed = true; }} />);
  fireEvent.click(screen.getByRole("button", { name: "Bump Second chat to front of queue" }));
  await waitFor(() => expect(refreshed).toBe(true));
  expect(calls).toEqual(["./api/queue/send-2/front"]);
});

test("refreshes stale queue state after a rejected bump", async () => {
  let refreshed = false;
  globalThis.fetch = Object.assign(async () => Response.json({ detail: "This item is no longer waiting in the queue." }, { status: 409 }), { preconnect: originalFetch.preconnect });
  render(<QueueFrontButton endpoint="./api/queue/gone/front" label="Gone" onMoved={async () => { refreshed = true; }} />);
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(refreshed).toBe(true));
  expect(screen.getByRole("button").hasAttribute("disabled")).toBe(false);
});
