import { mount } from "svelte";

import App from "./App.svelte";

const target = document.querySelector<HTMLElement>("#app");

if (!target) throw new Error("Missing #app mount target");

const serverName = target.dataset.serverName?.trim() || "local";

mount(App, {
  target,
  props: { serverName },
});

// The data/orchestration layer attaches after Svelte has mounted the stable shell.
await import("./app");
