import { mount } from "svelte";

import App from "./App.svelte";

const target = document.querySelector<HTMLElement>("#app");

if (!target) throw new Error("Missing #app mount target");

const serverName = target.dataset.serverName?.trim() || "local";

mount(App, {
  target,
  props: { serverName },
});

// Keep the existing behavior layer during the component migration. Importing it only
// after Svelte mounts guarantees its requiredElement() lookups see the stable shell.
await import("./app");
