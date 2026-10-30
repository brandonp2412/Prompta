import { expect, test } from "bun:test";
import { subscribeLiveUpdates } from "../src/ui/liveUpdates";

test("event-stream errors trigger fast repair while healthy streams retain a slow audit", () => {
  const originalSource = Object.getOwnPropertyDescriptor(globalThis, "EventSource");
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const handlers = new Map<string, Array<() => void>>();
  let repair: (() => void) | undefined;
  let period = 0;
  let closed = false;
  let cleared = false;
  let visibility = "visible";
  const documentHandlers = new Map<string, () => void>();
  class FakeEventSource {
    constructor(public url: string) {}
    addEventListener(name: string, callback: () => void) {
      handlers.set(name, [...(handlers.get(name) ?? []), callback]);
    }
    close() { closed = true; }
  }
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: FakeEventSource });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setInterval: (callback: () => void, ms: number) => { repair = callback; period = ms; return 7; },
      clearInterval: (id: number) => { if (id === 7) cleared = true; },
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      get visibilityState() { return visibility; },
      addEventListener: (name: string, callback: () => void) => { documentHandlers.set(name, callback); },
      removeEventListener: (name: string) => { documentHandlers.delete(name); },
    },
  });
  let offJobs: (() => void) | undefined;
  let offChats: (() => void) | undefined;
  try {
    let jobs = 0;
    let chats = 0;
    offJobs = subscribeLiveUpdates("jobs", () => { jobs += 1; });
    offChats = subscribeLiveUpdates("chats", () => { chats += 1; });
    expect(period).toBe(15_000);
    expect(repair).toBeDefined();
    const emit = (event: string) => { for (const callback of handlers.get(event) ?? []) callback(); };
    emit("sync");
    expect([jobs, chats]).toEqual([1, 1]);
    for (let i = 0; i < 7; i += 1) repair?.();
    expect([jobs, chats]).toEqual([1, 1]);
    repair?.();
    expect([jobs, chats]).toEqual([2, 2]);
    emit("error");
    emit("error"); // Duplicate browser disconnects must not issue extra GETs.
    repair?.();
    expect([jobs, chats]).toEqual([4, 4]);
    visibility = "hidden";
    repair?.();
    expect([jobs, chats]).toEqual([4, 4]);
    visibility = "visible";
    documentHandlers.get("visibilitychange")?.();
    expect([jobs, chats]).toEqual([5, 5]);
    emit("open");
    // The server's sync frame, not the transport open event, refreshes views.
    expect([jobs, chats]).toEqual([5, 5]);
    emit("sync");
    expect([jobs, chats]).toEqual([6, 6]);
    offJobs();
    offChats();
    expect(closed).toBe(true);
    expect(cleared).toBe(true);
  } finally {
    offJobs?.();
    offChats?.();
    for (const [name, descriptor] of [
      ["EventSource", originalSource], ["window", originalWindow], ["document", originalDocument],
    ] as const) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  }
});
