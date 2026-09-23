import { describe, expect, test } from "bun:test";

import {
  captureConversationViewport,
  conversationViewport,
  restoreConversationViewport,
} from "./browserAttachments.svelte.ts";

function fakeViewport({
  scrollTop,
  scrollHeight = 1200,
  clientHeight = 400,
}: {
  scrollTop: number;
  scrollHeight?: number;
  clientHeight?: number;
}) {
  return {
    scrollTop,
    scrollHeight,
    clientHeight,
  } as HTMLElement;
}

function attachViewport(element: HTMLElement) {
  const cleanup = conversationViewport()(element);

  return typeof cleanup === "function" ? cleanup : () => {};
}

describe("conversation viewport memory", () => {
  test("captures the current scroll position instead of resetting to the top", () => {
    const element = fakeViewport({ scrollTop: 275 });
    const cleanup = attachViewport(element);

    expect(captureConversationViewport()).toEqual({
      pinnedToBottom: false,
      scrollTop: 275,
    });

    cleanup();
  });

  test("restores a remembered position and defaults a new chat to the newest messages", () => {
    const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = (callback) => {
      callback(0);

      return 1;
    };

    const element = fakeViewport({ scrollTop: 0 });
    const cleanup = attachViewport(element);

    restoreConversationViewport({ pinnedToBottom: false, scrollTop: 325 });
    expect(element.scrollTop).toBe(325);

    restoreConversationViewport({ pinnedToBottom: false, scrollTop: 0 }, true);
    expect(element.scrollTop).toBe(element.scrollHeight);

    cleanup();
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  });

  test("treats a viewport already near the bottom as pinned to the latest message", () => {
    const element = fakeViewport({
      scrollTop: 790,
      scrollHeight: 1200,
      clientHeight: 400,
    });
    const cleanup = attachViewport(element);

    expect(captureConversationViewport()).toEqual({
      pinnedToBottom: true,
      scrollTop: 790,
    });

    cleanup();
  });
});
