import assert from "node:assert/strict";
import { test } from "node:test";
import { lintSvelteDom, lintTypeScriptDom } from "../scripts/lint-svelte-dom.mjs";

test("allows keyed lists, Svelte reactive state and element bindings", () => {
  const source = `<script>let items = $state([{ id: 1 }]); let pane;</script>
    <div bind:this={pane}>{#each items as item (item.id)}<span>{item.id}</span>{/each}</div>`;
  assert.deepEqual(lintSvelteDom(source), []);
});

test("rejects component-destroying Svelte key blocks", () => {
  const errors = lintSvelteDom("{#key chatId}<textarea></textarea>{/key}");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /No \{#key\} remount blocks/);
});

test("rejects raw HTML replacement", () => {
  const errors = lintSvelteDom("{@html message}");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /No \{@html\} DOM replacement/);
});

test("rejects DOM replacement in TypeScript modules while allowing bootstrap", () => {
  assert.deepEqual(lintTypeScriptDom('const app = document.querySelector<HTMLElement>("#app");', "src/ui/main.ts"), []);
  const errors = lintTypeScriptDom('document.body.replaceChildren(); element["outerHTML"] = html;');
  assert.equal(errors.length, 2);
  assert.match(errors.join("\n"), /replaceChildren/);
  assert.match(errors.join("\n"), /outerHTML/);
  assert.equal(lintTypeScriptDom('document.querySelector(".elsewhere")', "src/ui/main.ts").length, 1);
});

test("rejects imperative DOM replacement and manual queries", () => {
  const source = `<script>
    document.querySelector("#app").replaceChildren();
    element["innerHTML"] = markup;
  </script>`;
  const errors = lintSvelteDom(source);
  assert.equal(errors.length, 3);
  assert.match(errors.join("\n"), /querySelector/);
  assert.match(errors.join("\n"), /replaceChildren/);
  assert.match(errors.join("\n"), /innerHTML/);
});
