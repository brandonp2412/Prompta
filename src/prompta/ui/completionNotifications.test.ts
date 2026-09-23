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
    registration,
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
    completion.trackCompletions([
      {
        id: "chat-1",
        status: "complete",
        title: "Roadmap",
        completed_at: 100,
      },
    ]);
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].title).toBe("Prompta · GLASS");
    expect(browser.shown[0].options.body).toBe("Roadmap finished");

    completion.trackCompletions([
      {
        id: "chat-1",
        status: "complete",
        title: "Roadmap",
        completed_at: 100,
      },
    ]);
    completion.markActive("chat-1");
    completion.trackCompletions([
      {
        id: "chat-1",
        status: "complete",
        title: "Roadmap",
        completed_at: 100,
      },
    ]);
    await settle();

    expect(browser.shown).toHaveLength(1);
  });

  test("notifies a fast completion explicitly started by this client", async () => {
    const browser = browserNotifications();
    const completion = notifications();

    completion.markActive("chat-fast");
    completion.trackCompletions([
      {
        id: "chat-fast",
        status: "complete",
        title: "Fast run",
        completed_at: 200,
      },
    ]);
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].options.tag).toBe("prompta-finished-chat-fast");
  });

  test("registers Web Push so later completions do not depend on the page staying awake", async () => {
    const browser = browserNotifications();
    const calls = [];
    const keyBytes = Uint8Array.from({ length: 65 }, (_, index) => (index === 0 ? 4 : index));
    const publicKey = btoa(String.fromCharCode(...keyBytes))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    const subscription = {
      options: { applicationServerKey: keyBytes.buffer },
      async unsubscribe() {
        return true;
      },
      toJSON() {
        return {
          endpoint: "https://push.example.test/subscription",
          keys: { p256dh: "public-key", auth: "auth-secret" },
        };
      },
    };

    browser.registration.pushManager = {
      async getSubscription() {
        return null;
      },
      async subscribe(options) {
        expect(new Uint8Array(options.applicationServerKey)).toEqual(keyBytes);

        return subscription;
      },
    };

    replaceGlobal("fetch", async (url, options = {}) => {
      calls.push({ url, options });

      if (url === "api/push/public-key") {
        return {
          ok: true,
          async json() {
            return { public_key: publicKey };
          },
        };
      }

      return {
        ok: true,
        async json() {
          return {};
        },
      };
    });

    const completion = notifications();
    await completion.initialize();

    completion.trackCompletions([{ id: "chat-push", status: "active", title: "Mobile" }]);
    completion.trackCompletions([
      {
        id: "chat-push",
        status: "complete",
        title: "Mobile",
        completed_at: Date.now() / 1000 + 1,
      },
    ]);
    await settle();

    expect(browser.shown).toHaveLength(0);
    expect(calls.map((call) => call.url)).toEqual([
      "api/push/public-key",
      "api/push/subscriptions",
    ]);
    expect(calls[1].options.method).toBe("POST");
  });

  test("holds a completion until an in-flight permission request is granted", async () => {
    const browser = browserNotifications("default");
    const completion = notifications();

    const permission = completion.requestPermissionFromGesture();
    completion.markActive("chat-permission");
    completion.trackCompletions([
      {
        id: "chat-permission",
        status: "complete",
        title: "Permission run",
        completed_at: 300,
      },
    ]);
    await settle();

    expect(browser.shown).toHaveLength(0);

    browser.resolvePermission("granted");
    await permission;
    await settle();

    expect(browser.shown).toHaveLength(1);
    expect(browser.shown[0].options.body).toBe("Permission run finished");
  });
});
