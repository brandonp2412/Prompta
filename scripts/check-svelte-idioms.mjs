import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const browserBoundary = "browserAttachments.svelte.ts";

const sharedRules = [
  [/\bfrom\s+["']svelte\/store["']/g, "Use Svelte 5 runes instead of legacy svelte/store state."],
  [/\$:\s/g, "Use Svelte 5 runes instead of legacy $: reactive statements."],
];

const componentRules = [
  [/\{@html\b/g, "Render typed data with Svelte instead of {@html}."],
  [/\bbind:this\s*=/g, "Use a Svelte attachment instead of bind:this element references."],
  [/\bon:[A-Za-z][\w-]*\s*=/g, "Use Svelte 5 event properties instead of legacy on: directives."],
  [/\bclass:[A-Za-z][\w-]*\s*=/g, "Use class arrays/objects instead of class: directives."],
  [/\buse:[A-Za-z][\w-]*/g, "Use Svelte 5 attachments instead of actions."],
  [/\{@const\b/g, "Use Svelte 5 declaration tags instead of legacy {@const}."],
  [/\bexport\s+let\b/g, "Use $props() instead of legacy export let props."],
  [/<slot(?:\s|\/?>)/g, "Use snippets/render tags instead of legacy slots."],
  [/<svelte:component\b/g, "Use normal dynamic component expressions in Svelte 5."],
  [/\b(?:beforeUpdate|afterUpdate|onMount)\s*\(/g, "Use runes/attachments instead of component lifecycle hooks."],
];

const directDomRules = [
  [/\b(?:document|window)\./g, "Direct document/window access belongs in an explicit browser boundary."],
  [/\bmatchMedia\s*\(/g, "Use MediaQuery from svelte/reactivity instead of matchMedia()."],
  [/\.querySelector(?:All)?\s*\(/g, "Do not query component DOM manually."],
  [/\bcreateElement\s*\(/g, "Do not create component DOM manually."],
  [/\.(?:innerHTML|outerHTML|textContent|classList)\b/g, "Do not mutate rendered DOM manually."],
  [/\.(?:setAttribute|toggleAttribute)\s*\(/g, "Express attributes declaratively in Svelte."],
  [/\.(?:addEventListener|removeEventListener)\s*\(/g, "Own component events declaratively or in an attachment."],
  [/\.(?:focus|blur|setSelectionRange|showModal)\s*\(/g, "Imperative element APIs belong in a Svelte attachment."],
  [/\.scroll(?:Top|Height)\b/g, "Imperative scrolling belongs in a Svelte attachment."],
];

export function findSvelteIdiomViolations(source, file = "Component.svelte") {
  const name = path.basename(file);
  const component = file.endsWith(".svelte");
  const svelteModule = file.endsWith(".svelte.ts");
  const appOrchestrator = name === "app.ts";
  const rules = component || svelteModule ? [...sharedRules] : [];

  if (component) rules.push(...componentRules, ...directDomRules);
  else if (svelteModule && name !== browserBoundary) rules.push(...directDomRules);
  else if (appOrchestrator) rules.push(...directDomRules);

  const violations = [];

  for (const [pattern, message] of rules) {
    pattern.lastIndex = 0;
    let match;

    while ((match = pattern.exec(source)) !== null) {
      const before = source.slice(0, match.index);
      const line = before.split("\n").length;
      const column = match.index - before.lastIndexOf("\n");
      violations.push({ file, line, column, message });
      if (match[0].length === 0) pattern.lastIndex += 1;
    }
  }

  return violations;
}

function collectFiles(target) {
  const resolved = path.resolve(target);

  if (fs.statSync(resolved).isFile()) {
    return /\.svelte(?:\.ts)?$/.test(resolved) || path.basename(resolved) === "app.ts"
      ? [resolved]
      : [];
  }

  return fs
    .readdirSync(resolved, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? collectFiles(path.join(resolved, entry.name))
        : [path.join(resolved, entry.name)],
    )
    .filter(
      (file) => /\.svelte(?:\.ts)?$/.test(file) || path.basename(file) === "app.ts",
    );
}

if (import.meta.main) {
  const roots = process.argv.slice(2);
  const files = roots.length ? roots.flatMap(collectFiles) : collectFiles("src/ui");
  let violationCount = 0;

  for (const file of files) {
    const violations = findSvelteIdiomViolations(fs.readFileSync(file, "utf8"), file);
    violationCount += violations.length;

    for (const violation of violations) {
      console.error(
        violation.file +
          ":" +
          violation.line +
          ":" +
          violation.column +
          " " +
          violation.message,
      );
    }
  }

  if (violationCount) {
    console.error(
      "Found " +
        violationCount +
        " forbidden Svelte regression" +
        (violationCount === 1 ? "" : "s") +
        ".",
    );
    process.exitCode = 1;
  }
}
