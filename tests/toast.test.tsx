import React from "react";
import { afterEach, expect, test } from "bun:test";
import { signal } from "@preact/signals-core";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ToastHost from "../src/ui/ToastHost";
import {
  activeToast,
  dismissToast,
  notify,
  reportBackendReadFailure,
  reportBackendReadSuccess,
  resetBackendOutage,
  setLiveStreamDelayed,
  useToastSignal,
} from "../src/ui/toast";

afterEach(() => {
  cleanup();
  while (activeToast.peek()) dismissToast(activeToast.peek()!.id);
});

test("one accessible bottom toast replaces earlier feedback and can be dismissed", async () => {
  render(<ToastHost chatView />);
  act(() => {
    notify("Copied chat link", "success");
  });
  expect(screen.getByRole("status").textContent).toContain("Copied chat link");
  expect(document.querySelector(".toast-viewport.chat-view")).toBeTruthy();

  act(() => {
    notify("Copy failed", "error");
  });
  expect(screen.getByRole("alert").textContent).toContain("Copy failed");
  expect(screen.queryByText("Copied chat link")).toBeNull();
  await userEvent.setup().click(screen.getByRole("button", { name: "Dismiss notification" }));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("copy confirmation appears immediately even while an older error is visible", () => {
  render(<ToastHost chatView />);
  act(() => {
    notify("Previous failure", "error");
    notify("Chat link copied", "success");
  });
  expect(screen.getByRole("status").textContent).toContain("Chat link copied");
  expect(screen.queryByText("Previous failure")).toBeNull();
});

test("multiple errors are shown sequentially without stacking or losing them", async () => {
  render(<ToastHost chatView={false} />);
  act(() => {
    notify("First failure", "error");
    notify("Second failure", "error");
  });
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert").textContent).toContain("First failure");
  await userEvent.setup().click(screen.getByRole("button", { name: "Dismiss notification" }));
  expect(screen.getByRole("alert").textContent).toContain("Second failure");
});

test("immediate composer feedback replaces an older error without replaying it", async () => {
  render(<ToastHost chatView />);
  act(() => {
    notify("Continue in a new chat instead.", "error");
    notify("Queue receipt is uncertain.", "error", undefined, undefined, true);
  });
  expect(screen.getByRole("alert").textContent).toContain("Queue receipt is uncertain.");
  await userEvent.setup().click(screen.getByRole("button", { name: "Dismiss notification" }));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("signal errors become retryable toasts with no inline boxes", async () => {
  const failure = signal("");
  let retries = 0;
  function Source() {
    useToastSignal(failure, {
      action: {
        label: "Retry",
        onClick: () => {
          retries++;
        },
      },
    });
    return null;
  }
  render(
    <>
      <Source />
      <ToastHost chatView={false} />
    </>,
  );
  act(() => {
    failure.value = "Replies unavailable";
  });
  expect(screen.getByRole("alert").textContent).toContain("Replies unavailable");
  await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
  expect(retries).toBe(1);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("one deploy outage suppresses independent read failures until recovery", () => {
  resetBackendOutage();
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const timers = new Map<number, () => void>();
  let nextTimer = 0;
  globalThis.setTimeout = ((callback: () => void) => {
    const id = ++nextTimer;
    timers.set(id, callback);
    return id;
  }) as typeof setTimeout;
  globalThis.clearTimeout = ((id: number) => {
    timers.delete(id);
  }) as typeof clearTimeout;
  try {
    render(<ToastHost chatView />);
    act(() => {
      notify("Chat list unavailable", "error", undefined, 6500, false, true);
      reportBackendReadFailure();
      reportBackendReadFailure();
      setLiveStreamDelayed(true);
      notify("Pinned chats unavailable", "error", undefined, 6500, false, true);
      notify("Queue status unavailable", "error", undefined, 6500, false, true);
      notify("Saved replies unavailable", "error", undefined, 6500, false, true);
    });
    const outage = activeToast.peek();
    expect(outage?.message).toBe("Connection to Prompta interrupted. Reconnecting automatically.");
    expect(outage?.duration).toBe(0);
    expect(screen.getAllByRole("status")).toHaveLength(1);
    act(() => {
      reportBackendReadSuccess();
      setLiveStreamDelayed(false);
    });
    expect(activeToast.peek()?.id).toBe(outage?.id); // A good GET alone cannot end a rolling outage.
    act(() => {
      for (const callback of [...timers.values()]) callback();
    });
    expect(activeToast.peek()).toBeNull();
    act(() => {
      notify("Could not copy message", "error");
    });
    expect(screen.getByRole("alert").textContent).toContain("Could not copy message");
  } finally {
    resetBackendOutage();
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});
