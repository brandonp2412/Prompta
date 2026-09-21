import { afterEach, describe, expect, test } from "bun:test";

import { createLiveUpdates } from "./liveUpdates";

const savedGlobals = new Map();

function replaceGlobal(name, value) {
  if (!savedGlobals.has(name)) {
    savedGlobals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
  }
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
}

function restoreGlobals() {
  for (const [name, descriptor] of savedGlobals.entries()) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
  }
  savedGlobals.clear();
}

class FakeEventSource {
  static instances = [];
  listeners = new Map();
  closed = false;

  constructor(url) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type, data = "") {
    for (const listener of this.listeners.get(type) || []) {
      listener({ data });
    }
  }

  close() {
    this.closed = true;
  }
}

function installBrowser() {
  const windowListeners = new Map();
  const windowValue = {
    EventSource: FakeEventSource,
    addEventListener(type, listener) {
      const listeners = windowListeners.get(type) || [];
      listeners.push(listener);
      windowListeners.set(type, listeners);
    },
  };
  replaceGlobal("window", windowValue);
  replaceGlobal("EventSource", FakeEventSource);
  replaceGlobal("requestAnimationFrame", (callback) => {
    callback(0);
    return 1;
  });
  FakeEventSource.instances = [];
}

afterEach(() => {
  restoreGlobals();
  FakeEventSource.instances = [];
});

describe("live presence", () => {
  test("moves online to offline on a stale heartbeat and recovers after a new heartbeat", async () => {
    installBrowser();
    const statuses = [];
    let streamErrors = 0;
    const live = createLiveUpdates({
      loadChats: async () => {},
      loadServerIdentity: async () => {},
      setServerStatus: (server, online) => statuses.push({ server, online }),
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
