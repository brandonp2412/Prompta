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
