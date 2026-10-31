import { expect, test } from "bun:test";
import { subscribeLiveStatus } from "../src/ui/liveUpdates";

test("an open socket without a server frame remains degraded", () => {
  const originalSource = Object.getOwnPropertyDescriptor(globalThis, "EventSource");
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  let statusTimer: (() => void) | undefined;
  const events = new Map<string, () => void>();
  const received: boolean[] = [];
  class SilentStream {
    readyState = 1;
    addEventListener(name: string, callback: () => void) {
      events.set(name, callback);
    }
    close() {
      this.readyState = 2;
    }
  }
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: SilentStream });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setInterval: () => 1,
      clearInterval: () => {},
      setTimeout: (callback: () => void, delay: number) => {
        if (delay === 10000) statusTimer = callback;
        return delay;
      },
      clearTimeout: (id: number) => {
        if (id === 10000) statusTimer = undefined;
      },
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      visibilityState: "visible",
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  });
  try {
    const unsubscribe = subscribeLiveStatus((value) => received.push(value));
    try {
      events.get("open")?.();
      statusTimer?.();
      expect(received).toEqual([false, true]);
      events.get("sync")?.();
      expect(received).toEqual([false, true, false]);
    } finally {
      unsubscribe();
    }
  } finally {
    for (const [name, descriptor] of [
      ["EventSource", originalSource],
      ["window", originalWindow],
      ["document", originalDocument],
    ] as const) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  }
});
