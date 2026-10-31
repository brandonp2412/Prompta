import { expect, test } from "bun:test";
import {
  retryLiveConnection,
  subscribeLiveUpdates,
  subscribeLiveStatus,
} from "../src/ui/liveUpdates";

type FakeStream = { readyState: number; closed: boolean; emit: (name: string) => void };

function withFakeStream(
  run: (tools: {
    instances: FakeStream[];
    timers: Map<number, { ms: number; callback: () => void }>;
    tick: (milliseconds: number) => void;
    fire: (milliseconds: number) => void;
    fireWindow: (name: string) => void;
  }) => void,
) {
  const originalSource = Object.getOwnPropertyDescriptor(globalThis, "EventSource");
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const originalNow = Date.now;
  const timers = new Map<number, { ms: number; callback: () => void }>();
  const instances: FakeStream[] = [];
  const windowHandlers = new Map<string, Set<() => void>>();
  let now = 1000;
  let nextTimer = 0;
  class LocalFakeStream {
    readyState = 0;
    closed = false;
    handlers = new Map<string, Array<() => void>>();
    constructor(public url: string) {
      instances.push(this);
    }
    addEventListener(name: string, callback: () => void) {
      this.handlers.set(name, [...(this.handlers.get(name) ?? []), callback]);
    }
    emit(name: string) {
      for (const callback of this.handlers.get(name) ?? []) callback();
    }
    close() {
      this.closed = true;
      this.readyState = 2;
    }
  }
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: LocalFakeStream });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setInterval: () => ++nextTimer,
      clearInterval: () => {},
      setTimeout: (callback: () => void, ms: number) => {
        const id = ++nextTimer;
        timers.set(id, { callback, ms });
        return id;
      },
      clearTimeout: (id: number) => timers.delete(id),
      addEventListener: (name: string, callback: () => void) => {
        if (!windowHandlers.has(name)) windowHandlers.set(name, new Set());
        windowHandlers.get(name)?.add(callback);
      },
      removeEventListener: (name: string, callback: () => void) => {
        windowHandlers.get(name)?.delete(callback);
      },
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
  Date.now = () => now;
  try {
    run({
      instances,
      timers,
      tick: (milliseconds: number) => {
        now += milliseconds;
      },
      fire: (milliseconds: number) => {
        const entry = [...timers.entries()].find(([, timer]) => timer.ms === milliseconds);
        expect(entry).toBeDefined();
        if (!entry) return;
        timers.delete(entry[0]);
        entry[1].callback();
      },
      fireWindow: (name: string) => {
        for (const callback of windowHandlers.get(name) ?? []) callback();
      },
    });
  } finally {
    Date.now = originalNow;
    for (const [name, descriptor] of [
      ["EventSource", originalSource],
      ["window", originalWindow],
      ["document", originalDocument],
    ] as const) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  }
}

test("terminal SSE failures reopen once, ignore stale events and clean up on unmount", () => {
  withFakeStream(({ instances, timers, fire }) => {
    let updates = 0;
    const off = subscribeLiveUpdates("chats", () => {
      updates += 1;
    });
    try {
      const first = instances[0];
      expect(first).toBeDefined();
      first?.emit("open");
      first?.emit("sync");
      expect(updates).toBe(1);
      if (first) first.readyState = 2;
      first?.emit("error");
      first?.emit("error");
      expect([...timers.values()].filter((timer) => timer.ms === 2000).length).toBe(1);
      fire(2000);
      expect(instances.length).toBe(2);
      expect(first?.closed).toBe(true);
      first?.emit("sync");
      expect(updates).toBe(2); // One immediate read when a healthy connection dropped.
      instances[1]?.emit("open");
      instances[1]?.emit("sync");
      expect(updates).toBe(3);
      retryLiveConnection();
      expect(instances.length).toBe(3);
      expect(instances[1]?.closed).toBe(true);
      expect(updates).toBe(4); // Explicit refresh repairs local reads immediately.
      instances[1]?.emit("sync");
      expect(updates).toBe(4); // A retired source cannot update current views.
      instances[2]?.emit("open");
      instances[2]?.emit("sync");
      expect(updates).toBe(5);
    } finally {
      off();
    }
    expect(instances[2]?.closed).toBe(true);
    expect(timers.size).toBe(0);
  });
});

test("network return immediately repairs an offline stream without duplicate listeners", () => {
  withFakeStream(({ instances, fireWindow }) => {
    let updates = 0;
    const off = subscribeLiveUpdates("chats", () => {
      updates += 1;
    });
    try {
      instances[0]?.emit("open");
      instances[0]?.emit("sync");
      expect(updates).toBe(1);
      fireWindow("offline");
      fireWindow("online");
      expect(instances.length).toBe(2);
      expect(instances[0]?.closed).toBe(true);
      instances[0]?.emit("sync");
      expect(updates).toBe(2); // Skip futile local reads while explicitly offline.
      instances[1]?.emit("open");
      instances[1]?.emit("sync");
      expect(updates).toBe(3);
      fireWindow("online");
      expect(instances.length).toBe(2); // No repeated reconnect after recovery.
    } finally {
      off();
    }
  });
});

test("offline mode cancels reconnect attempts and resumes once online", () => {
  withFakeStream(({ instances, timers, fireWindow, fire }) => {
    let updates = 0;
    const off = subscribeLiveUpdates("chats", () => {
      updates += 1;
    });
    try {
      instances[0]?.emit("sync");
      if (instances[0]) instances[0].readyState = 2;
      instances[0]?.emit("error");
      expect([...timers.values()].some((timer) => timer.ms === 2000)).toBe(true);
      fireWindow("offline");
      expect([...timers.values()].some((timer) => timer.ms === 2000)).toBe(false);
      expect(updates).toBe(2);
      fire(10000);
      expect(instances).toHaveLength(1);
      fireWindow("online");
      expect(instances).toHaveLength(2);
      expect(instances[0]?.closed).toBe(true);
      expect(updates).toBe(3);
    } finally {
      off();
    }
  });
});

test("returning from a hidden tab restores the stalled-stream watchdog", () => {
  withFakeStream(({ instances, tick, fire, fireWindow, timers }) => {
    const off = subscribeLiveUpdates("chats", () => {});
    try {
      instances[0]?.emit("ping");
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
      tick(59_000);
      fire(60_000);
      expect([...timers.values()].some((timer) => timer.ms === 60_000)).toBe(false);

      Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
      fireWindow("pageshow");
      expect([...timers.values()].some((timer) => timer.ms === 60_000)).toBe(true);
      tick(2_000);
      fire(60_000);
      fire(2_000);
      expect(instances).toHaveLength(2);
      expect(instances[0]?.closed).toBe(true);
    } finally {
      off();
    }
  });
});

test("a silent stalled SSE connection is replaced and degraded status heals", () => {
  withFakeStream(({ instances, tick, fire }) => {
    const status: boolean[] = [];
    const off = subscribeLiveStatus((delayed) => {
      status.push(delayed);
    });
    try {
      instances[0]?.emit("open");
      instances[0]?.emit("ping");
      tick(61000);
      fire(60000);
      fire(2000);
      expect(instances.length).toBe(2);
      expect(instances[0]?.closed).toBe(true);
      fire(10000);
      expect(status).toEqual([false, true]);
      instances[1]?.emit("open");
      expect(status).toEqual([false, true]);
      instances[1]?.emit("sync");
      expect(status).toEqual([false, true, false]);
    } finally {
      off();
    }
  });
});
