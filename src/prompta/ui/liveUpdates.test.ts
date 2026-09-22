import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { createLiveUpdates } from "./liveUpdates";

type StreamListener = (event: { data: string }) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners = new Map<string, StreamListener[]>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: StreamListener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, data = "") {
    for (const listener of this.listeners.get(type) || []) listener({ data });
  }

  close() {
    this.closed = true;
  }
}

let windowListeners = new Map<string, Array<() => void>>();

function emitWindow(type: string) {
  for (const listener of windowListeners.get(type) || []) listener();
}

const originalWindow = globalThis.window;

const originalEventSource = globalThis.EventSource;

beforeEach(() => {
  FakeEventSource.instances = [];
  windowListeners = new Map();
  const fakeWindow = {
    EventSource: FakeEventSource,
    addEventListener(type: string, listener: () => void) {
      const listeners = windowListeners.get(type) || [];
      listeners.push(listener);
      windowListeners.set(type, listeners);
    },
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: fakeWindow,
  });
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    value: FakeEventSource,
  });
});

afterEach(() => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: originalWindow,
  });
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    value: originalEventSource,
  });
});

describe("live chat synchronization", () => {
  test("refreshes immediately and coalesces a newer SSE refresh behind an in-flight load", async () => {
    let loads = 0;
    let releaseFirst!: () => void;
    const firstLoad = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    const serverStates: Array<[string, boolean]> = [];
    const heads: string[] = [];

    const liveUpdates = createLiveUpdates({
      loadChats: () => {
        loads += 1;
        return loads === 1 ? firstLoad : Promise.resolve();
      },
      loadServerIdentity: () => Promise.resolve(),
      setServerStatus: (server: string, online: boolean) => serverStates.push([server, online]),
      observeHead: (head: string) => heads.push(head),
      refreshDisplayedTimes: () => {},
      onStreamError: () => {},
      onPageShow: () => {},
    });

    liveUpdates.start();
    const stream = FakeEventSource.instances[0];
    stream.emit("refresh", JSON.stringify({ server: "glass", online: true, head: "abc123" }));

    expect(loads).toBe(1);
    expect(serverStates).toEqual([["glass", true]]);
    expect(heads).toEqual(["abc123"]);

    stream.emit("refresh", JSON.stringify({ server: "glass", online: true, head: "def456" }));
    expect(loads).toBe(1);

    releaseFirst();
    await Promise.resolve();
    await Promise.resolve();

    expect(loads).toBe(2);
    liveUpdates.stop();
  });

  test("reconnects and refreshes after a page lifecycle restore", async () => {
    let loads = 0;
    let identityLoads = 0;
    let pageShows = 0;

    const liveUpdates = createLiveUpdates({
      loadChats: async () => {
        loads += 1;
      },
      loadServerIdentity: async () => {
        identityLoads += 1;
      },
      setServerStatus: () => {},
      observeHead: () => {},
      refreshDisplayedTimes: () => {},
      onStreamError: () => {},
      onPageShow: () => {
        pageShows += 1;
      },
    });

    liveUpdates.start();
    expect(FakeEventSource.instances).toHaveLength(1);

    const firstStream = FakeEventSource.instances[0];
    emitWindow("pagehide");
    expect(firstStream.closed).toBe(true);

    emitWindow("pageshow");
    await Promise.resolve();

    expect(pageShows).toBe(1);
    expect(identityLoads).toBe(1);
    expect(loads).toBe(1);
    expect(FakeEventSource.instances).toHaveLength(2);

    liveUpdates.stop();
  });
});

describe("live presence", () => {
  test("moves online to offline on a stale heartbeat and recovers after a new heartbeat", async () => {
    const statuses: Array<{ server: string; online: boolean }> = [];
    let streamErrors = 0;
    const live = createLiveUpdates({
      loadChats: async () => {},
      loadServerIdentity: async () => {},
      setServerStatus: (server: string, online: boolean) => statuses.push({ server, online }),
      observeHead: () => {},
      refreshDisplayedTimes: () => {},
      onStreamError: () => {
        streamErrors += 1;
      },
      onPageShow: () => {},
      presenceStaleMs: 15,
      presenceCheckMs: 5,
    });

    live.start();
    const events = FakeEventSource.instances[0];
    events.emit("refresh", JSON.stringify({ server: "glass", online: true, head: "abc123" }));
    expect(statuses.at(-1)).toEqual({ server: "glass", online: true });

    await new Promise((resolve) => setTimeout(resolve, 35));
    expect(statuses.at(-1)).toEqual({ server: "glass", online: false });
    expect(streamErrors).toBeGreaterThan(0);

    events.emit("heartbeat", JSON.stringify({ server: "glass", online: true }));
    expect(statuses.at(-1)).toEqual({ server: "glass", online: true });

    events.emit("error");
    expect(statuses.at(-1)).toEqual({ server: "glass", online: false });

    events.emit("refresh", JSON.stringify({ server: "glass", online: true, head: "def456" }));
    expect(statuses.at(-1)).toEqual({ server: "glass", online: true });

    live.stop();
    expect(events.closed).toBe(true);
  });
});
