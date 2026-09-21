import { afterEach, describe, expect, test } from "bun:test";

import { createCompletionNotifications } from "./completionNotifications";

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

function browserNotifications(initialPermission = "granted") {
  let permission = initialPermission;
  let permissionResolver = null;
  const shown = [];

  class FakeNotification {
    static get permission() {
      return permission;
    }

    static requestPermission() {
      if (permission !== "default") return Promise.resolve(permission);
      return new Promise((resolve) => {
        permissionResolver = (next) => {
          permission = next;
          resolve(next);
        };
      });
    }

    constructor(title, options) {
      shown.push({ title, options, source: "window" });
    }
  }

  const registration = {
    async showNotification(title, options) {
      shown.push({ title, options, source: "service-worker" });
    },
  };

  replaceGlobal("Notification", FakeNotification);
  replaceGlobal("window", { Notification: FakeNotification });
  replaceGlobal("navigator", {
    serviceWorker: {
      getRegistration: async () => registration,
      ready: Promise.resolve(registration),
    },
  });
  replaceGlobal("location", { hostname: "glass" });

  return {
    shown,
    resolvePermission(next) {
      permissionResolver?.(next);
    },
  };
}

function notifications() {
  return createCompletionNotifications({
    displayServerName: (value) => String(value).toUpperCase(),
    getServerName: () => "glass",
    chatTitle: (chat) => chat.title || chat.id,
  });
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  restoreGlobals();
});

describe("completion notifications", () => {
  test("notifies once when an observed active chat completes", async () => {
    const browser = browserNotifications();
    const completion = notifications();

    completion.trackCompletions([{ id: "chat-1", status: "active", title: "Roadmap" }]);
    completion.trackCompletions([{
      id: "chat-1",
      status: "complete",
      title: "Roadmap",
      completed_at: 100,
    }]);
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].title).toBe("Prompta · GLASS");
    expect(browser.shown[0].options.body).toBe("Roadmap finished");

    completion.trackCompletions([{
      id: "chat-1",
      status: "complete",
      title: "Roadmap",
      completed_at: 100,
    }]);
    completion.markActive("chat-1");
    completion.trackCompletions([{
      id: "chat-1",
      status: "complete",
      title: "Roadmap",
      completed_at: 100,
    }]);
    await settle();

    expect(browser.shown).toHaveLength(1);
  });

  test("notifies a fast completion explicitly started by this client", async () => {
    const browser = browserNotifications();
    const completion = notifications();

    completion.markActive("chat-fast");
    completion.trackCompletions([{
      id: "chat-fast",
      status: "complete",
      title: "Fast run",
      completed_at: 200,
    }]);
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].options.tag).toBe("prompta-finished-chat-fast");
  });

  test("holds a completion until an in-flight permission request is granted", async () => {
    const browser = browserNotifications("default");
    const completion = notifications();

    const permission = completion.requestPermissionFromGesture();
    completion.markActive("chat-permission");
    completion.trackCompletions([{
      id: "chat-permission",
      status: "complete",
      title: "Permission run",
      completed_at: 300,
    }]);
    await settle();

    expect(browser.shown).toHaveLength(0);

    browser.resolvePermission("granted");
    await permission;
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].options.body).toBe("Permission run finished");
  });
});
