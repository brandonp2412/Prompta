
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

export function lintReactDom(source, filename = "<inline>.tsx") {
  const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true,
    filename.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const errors = [];
  function report(node, message) {
    const line = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;
    errors.push(`${filename}:${line}: ${message}`);
  }
  function visit(node) {
    let name = null;
    if (ts.isPropertyAccessExpression(node)) name = node.name.text;
    if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression)) name = node.argumentExpression.text;

    if (forbiddenMembers.has(name)) report(node, `Imperative DOM mutation (${name}) breaks React-owned DOM continuity.`);
    if (forbiddenQueries.has(name)) {
      const bootstrap = filename.endsWith("/main.tsx") && name === "querySelector" &&
        ts.isPropertyAccessExpression(node) && node.expression.getText(tree) === "document" &&
        node.parent && ts.isCallExpression(node.parent) && node.parent.arguments.length === 1 &&
        node.parent.arguments[0].getText(tree) === '"#app"';
      if (!bootstrap) report(node, `Imperative DOM lookup (${name}) bypasses React refs.`);
    }
    if (name === "write" && ts.isPropertyAccessExpression(node) &&
        node.expression.getText(tree) === "document") report(node, "document.write replaces React-owned DOM.");
    if (ts.isJsxAttribute(node) && node.name.text === "dangerouslySetInnerHTML") {
      report(node, "No dangerouslySetInnerHTML: render untrusted responses as React text/elements.");
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
  return errors;
}

function uiFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const filepath = join(dir, entry.name);
    return entry.isDirectory() ? uiFiles(filepath) : entry.isFile() && /\.tsx?$/.test(filepath) ? [filepath] : [];
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const files = uiFiles(join(projectRoot, "src/ui"));
  const errors = files.flatMap((file) => lintReactDom(readFileSync(file, "utf8"), relative(projectRoot, file)));
  if (errors.length) {
    console.error(errors.join("\n"));
    process.exitCode = 1;
  } else {
    console.log(`React DOM continuity lint passed (${files.length} UI source files).`);
  }
}
