import { describe, expect, test } from "bun:test";

import { findSvelteIdiomViolations } from "./check-svelte-idioms.mjs";

describe("Svelte idiom guard", () => {
  test("allows rune-based declarative Svelte", () => {
    const source = `<script lang="ts">
      let { value }: { value: string } = $props();
      let count = $state(0);
      const doubled = $derived(count * 2);
    </script>
    <button class={["item", { active: count > 0 }]} onclick={() => count += 1}>{value} {doubled}</button>`;

    expect(findSvelteIdiomViolations(source, "Example.svelte")).toEqual([]);
  });

  test("rejects legacy Svelte APIs", () => {
    const source = `<script>
      import { onMount } from "svelte";
      import { writable } from "svelte/store";
      export let value;
      $: doubled = value * 2;
      onMount(() => {});
    </script>
    <div bind:this={node} class:active={value} on:click={() => {}} use:legacy>
      {@html value}
      {@const answer = 42}
      <slot />
    </div>`;

    const messages = findSvelteIdiomViolations(source, "Legacy.svelte").map(
      (violation) => violation.message,
    );

    expect(messages.length).toBeGreaterThanOrEqual(8);
    expect(messages.some((message) => message.includes("{@html}"))).toBe(true);
    expect(messages.some((message) => message.includes("svelte/store"))).toBe(true);
    expect(messages.some((message) => message.includes("bind:this"))).toBe(true);
  });

  test("rejects direct component DOM manipulation", () => {
    const source = `<script>
      const node = document.querySelector(".thing");
      node.textContent = "changed";
      node.classList.add("active");
      node.focus();
      matchMedia("(pointer: coarse)");
    </script>`;

    const violations = findSvelteIdiomViolations(source, "DirectDom.svelte");

    expect(violations.length).toBeGreaterThanOrEqual(5);
  });

  test("allows imperative browser APIs only in the attachment boundary", () => {
    const source = `export function attachment() {
      return (element) => {
        element.addEventListener("scroll", () => {});
        element.focus();
        element.scrollTop = element.scrollHeight;
      };
    }`;

    expect(findSvelteIdiomViolations(source, "browserAttachments.svelte.ts")).toEqual([]);
    expect(findSvelteIdiomViolations(source, "featureState.svelte.ts").length).toBeGreaterThan(0);
  });

  test("keeps app.ts orchestration free of view DOM access", () => {
    expect(
      findSvelteIdiomViolations(
        'const node = document.querySelector("#messageInput"); node.hidden = true;',
        "app.ts",
      ).length,
    ).toBeGreaterThanOrEqual(2);
    expect(findSvelteIdiomViolations("setTimeout(run, 10);", "app.ts")).toEqual([]);
  });

});
