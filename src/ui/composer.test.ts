import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const composerSource = readFileSync(new URL("./Composer.svelte", import.meta.url), "utf8");

test("plain Enter stays a textarea newline and submit remains explicit", () => {
  expect(composerSource).not.toContain("!mobileInput.current");
  expect(composerSource).not.toContain('import { MediaQuery } from "svelte/reactivity"');
  expect(composerSource.match(/appActions\.onSubmit\(\)/g)?.length).toBe(1);
  expect(composerSource).toContain(
    'event.key === "Tab" || (event.key === "Enter" && !event.isComposing)',
  );
});

test("slash autocomplete keeps native textarea semantics", () => {
  expect(composerSource).not.toContain('role="combobox"');
  expect(composerSource).not.toContain("aria-expanded={slashOpen}");
  expect(composerSource).toContain('aria-controls={slashOpen ? "slashMenu" : undefined}');
  expect(composerSource).toContain('aria-autocomplete="list"');
  expect(composerSource).toContain(
    "aria-activedescendant={slashOpen && activeCommand ? activeCommand.id : undefined}",
  );
});

test("slash autocomplete includes the /every compatibility alias", () => {
  expect(composerSource).toContain('command: "/every "');
  expect(composerSource).toContain('name: "/every"');
  expect(composerSource).toContain('id: "slashCommandEvery"');
});
