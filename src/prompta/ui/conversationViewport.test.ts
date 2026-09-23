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
    children: [],
    addEventListener: () => {},
    removeEventListener: () => {},
  } as unknown as HTMLElement;
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

  test("applies a new chat's bottom position before deferred rendering can recapture scroll", () => {
    const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
    const queuedFrames: FrameRequestCallback[] = [];

    globalThis.requestAnimationFrame = (callback) => {
      queuedFrames.push(callback);

      return queuedFrames.length;
    };

    const element = fakeViewport({ scrollTop: 275 });
    const cleanup = attachViewport(element);

    restoreConversationViewport({ pinnedToBottom: false, scrollTop: 0 }, true);
    expect(element.scrollTop).toBe(element.scrollHeight);

    cleanup();
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  });

  test("keeps a pinned chat at the newest message while late content changes its height", () => {
    const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
    const originalResizeObserver = globalThis.ResizeObserver;
    let resizeCallback: ResizeObserverCallback | null = null;

    globalThis.requestAnimationFrame = (callback) => {
      callback(0);

      return 1;
    };
    globalThis.ResizeObserver = class {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback;
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    } as typeof ResizeObserver;

    const element = fakeViewport({
      scrollTop: 800,
      scrollHeight: 1200,
      clientHeight: 400,
    });
    const cleanup = attachViewport(element);

    element.scrollHeight = 1600;
    resizeCallback?.([], {} as ResizeObserver);
    expect(element.scrollTop).toBe(1600);

    cleanup();
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.ResizeObserver = originalResizeObserver;
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
