import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "svelte/compiler";
import ts from "typescript";

const forbiddenMembers = new Set([
  "innerHTML", "outerHTML", "replaceChildren", "insertAdjacentHTML",
  "insertAdjacentElement", "replaceWith", "replaceChild", "appendChild",
  "removeChild", "insertBefore", "append", "prepend", "remove",
]);
const forbiddenQueries = new Set([
  "querySelector", "querySelectorAll", "getElementById",
  "getElementsByClassName", "getElementsByTagName",
]);

function memberName(node) {
  if (!node?.property) return null;
  if (!node.computed && node.property.type === "Identifier") return node.property.name;
  if (node.computed && node.property.type === "Literal") return node.property.value;
  return null;
}

export function lintSvelteDom(source, filename = "<inline>") {
  const ast = parse(source, { filename, modern: true });
  const errors = [];
  const visited = new WeakSet();
  function report(node, message) {
    const line = source.slice(0, node.start ?? 0).split("\n").length;
    errors.push(`${filename}:${line}: ${message}`);
  }
  function visit(node) {
    if (node === null || typeof node !== "object" || visited.has(node)) return;
    visited.add(node);
    if (Array.isArray(node)) {
      for (const child of node) visit(child);
      return;
    }
    if (node.type === "KeyBlock") {
      report(node, "No {#key} remount blocks: preserve Svelte component identity across navigation.");
    }
    if (node.type === "HtmlTag") {
      report(node, "No {@html} DOM replacement: use Svelte-owned markup and reactive state.");
    }
    if (node.type === "MemberExpression") {
      const name = memberName(node);
      if (forbiddenMembers.has(name)) {
        report(node, `No imperative DOM mutation (${name}): let Svelte update existing nodes.`);
      }
      if (forbiddenQueries.has(name)) {
        report(node, `No imperative DOM lookup (${name}): use Svelte bindings/attachments.`);
      }
      if (name === "write" && node.object?.type === "Identifier" && node.object.name === "document") {
        report(node, "No document.write: let Svelte own the document.");
      }
    }
    for (const value of Object.values(node)) visit(value);
  }
  visit(ast);
  return errors;
}

export function lintTypeScriptDom(source, filename = "<inline>.ts") {
  const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const errors = [];
  function report(node, message) {
    const line = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;
    errors.push(`${filename}:${line}: ${message}`);
  }
  function visit(node) {
    let name = null;
    if (ts.isPropertyAccessExpression(node)) name = node.name.text;
    if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression)) {
      name = node.argumentExpression.text;
    }
    if (forbiddenMembers.has(name)) {
      report(node, `No imperative DOM mutation (${name}): let Svelte update existing nodes.`);
    }
    if (forbiddenQueries.has(name)) {
      const bootstrap = filename.endsWith("/main.ts") && name === "querySelector" &&
        ts.isPropertyAccessExpression(node) && node.expression.getText(tree) === "document" &&
        node.parent && ts.isCallExpression(node.parent) &&
        node.parent.arguments.length === 1 && node.parent.arguments[0].getText(tree) === '"#app"';
      if (!bootstrap) report(node, `No imperative DOM lookup (${name}): use Svelte bindings/attachments.`);
    }
    if (name === "write" && ts.isPropertyAccessExpression(node) &&
        node.expression.getText(tree) === "document") {
      report(node, "No document.write: let Svelte own the document.");
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
  return errors;
}

function svelteFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? svelteFiles(path) : entry.isFile() && /\.(svelte|tsx?)$/.test(path) ? [path] : [];
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const files = svelteFiles(join(projectRoot, "src/ui"));
  const errors = files.flatMap((file) => {
    const source = readFileSync(file, "utf8");
    const name = relative(projectRoot, file);
    return file.endsWith(".svelte") ? lintSvelteDom(source, name) : lintTypeScriptDom(source, name);
  });
  if (errors.length) {
    console.error(errors.join("\n"));
    process.exitCode = 1;
  } else {
    console.log(`Svelte DOM identity lint passed (${files.length} UI source files).`);
  }
}
