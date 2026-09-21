import { afterEach, describe, expect, test } from "bun:test";

import { createDeploymentMonitor } from "./deploymentMonitor";

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

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  restoreGlobals();
});

describe("deployment monitor", () => {
  test("reloads immediately when the deployed head changes", async () => {
    let updates = 0;
    let reloads = 0;
    replaceGlobal("navigator", {
      serviceWorker: {
        getRegistration: async () => ({
          update: async () => {
            updates += 1;
          },
        }),
      },
    });
    replaceGlobal("window", {
      location: {
        reload() {
          reloads += 1;
        },
      },
    });

    const monitor = createDeploymentMonitor();
    monitor.observeHead("aaaaaaaa");
    monitor.observeHead("bbbbbbbb");
    await settle();

    expect(updates).toBe(1);
    expect(reloads).toBe(1);

    monitor.observeHead("bbbbbbbb");
    await settle();

    expect(updates).toBe(1);
    expect(reloads).toBe(1);
  });

  test("registers the service worker without HTTP cache reuse", async () => {
    const registrations = [];
    replaceGlobal("navigator", {
      serviceWorker: {
        register: async (...args) => {
          registrations.push(args);
        },
      },
    });

    createDeploymentMonitor().registerServiceWorker();
    await settle();

    expect(registrations).toEqual([["./sw.js", { updateViaCache: "none" }]]);
  });
});
