import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import ts from "typescript";

const assignmentKinds = new Set([
  ts.SyntaxKind.EqualsToken,
  ts.SyntaxKind.PlusEqualsToken,
  ts.SyntaxKind.MinusEqualsToken,
  ts.SyntaxKind.AsteriskEqualsToken,
  ts.SyntaxKind.AsteriskAsteriskEqualsToken,
  ts.SyntaxKind.SlashEqualsToken,
  ts.SyntaxKind.PercentEqualsToken,
  ts.SyntaxKind.LessThanLessThanEqualsToken,
  ts.SyntaxKind.GreaterThanGreaterThanEqualsToken,
  ts.SyntaxKind.GreaterThanGreaterThanGreaterThanEqualsToken,
  ts.SyntaxKind.AmpersandEqualsToken,
  ts.SyntaxKind.BarEqualsToken,
  ts.SyntaxKind.CaretEqualsToken,
  ts.SyntaxKind.BarBarEqualsToken,
  ts.SyntaxKind.AmpersandAmpersandEqualsToken,
  ts.SyntaxKind.QuestionQuestionEqualsToken,
]);

export function findDomRebuildViolations(source, file = "input.ts") {
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const violations = [];

  visit(sourceFile);

  return violations;

  function visit(node) {
    if (
      ts.isBinaryExpression(node) &&
      assignmentKinds.has(node.operatorToken.kind) &&
      (ts.isPropertyAccessExpression(node.left) || ts.isElementAccessExpression(node.left))
    ) {
      const property = memberName(node.left);

      if (property === "innerHTML" && !isDetachedTemplateReceiver(memberReceiver(node.left))) {
        report(node.left, "Do not assign innerHTML on mounted DOM; patch existing nodes in place.");
      } else if (property === "outerHTML") {
        report(node.left, "Do not assign outerHTML; patch the existing DOM node in place.");
      }
    }

    if (
      ts.isCallExpression(node) &&
      (ts.isPropertyAccessExpression(node.expression) ||
        ts.isElementAccessExpression(node.expression))
    ) {
      const property = memberName(node.expression);
      const receiver = memberReceiver(node.expression);

      if (property === "replaceChildren") {
        report(
          node.expression,
          "Do not replaceChildren(); reconcile existing child nodes in place.",
        );
      } else if (
        (property === "write" || property === "writeln") &&
        ts.isIdentifier(receiver) &&
        receiver.text === "document"
      ) {
        report(node.expression, "Do not use document.write(); it rebuilds the document.");
      }
    }

    node.forEachChild(visit);
  }

  function report(node, message) {
    const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    violations.push({
      file,
      line: position.line + 1,
      column: position.character + 1,
      message,
    });
  }

  function isDetachedTemplateReceiver(node) {
    if (!ts.isIdentifier(node)) return false;

    let scope = node.parent;

    while (scope) {
      if (ts.isFunctionLike(scope)) {
        if (
          scope.parameters.some(
            (parameter) => ts.isIdentifier(parameter.name) && parameter.name.text === node.text,
          )
        ) {
          return false;
        }
      }

      if (ts.isBlock(scope) || ts.isSourceFile(scope)) {
        for (const statement of scope.statements) {
          if (statement.getStart(sourceFile) >= node.getStart(sourceFile)) break;
          if (!ts.isVariableStatement(statement)) continue;

          const declaration = statement.declarationList.declarations.find(
            (candidate) => ts.isIdentifier(candidate.name) && candidate.name.text === node.text,
          );

          if (declaration) {
            return Boolean(
              declaration.initializer && isCreateTemplateCall(declaration.initializer),
            );
          }
        }
      }

      scope = scope.parent;
    }

    return false;
  }
}

function isCreateTemplateCall(node) {
  if (
    !ts.isCallExpression(node) ||
    !ts.isPropertyAccessExpression(node.expression) ||
    node.expression.name.text !== "createElement" ||
    !ts.isIdentifier(node.expression.expression) ||
    node.expression.expression.text !== "document" ||
    node.arguments.length !== 1
  ) {
    return false;
  }

  const argument = node.arguments[0];

  return ts.isStringLiteralLike(argument) && argument.text.toLowerCase() === "template";
}

function memberName(node) {
  if (ts.isPropertyAccessExpression(node)) return node.name.text;

  const argument = node.argumentExpression;

  return argument && ts.isStringLiteralLike(argument) ? argument.text : "";
}

function memberReceiver(node) {
  return node.expression;
}

function collectFiles(target) {
  const resolved = path.resolve(target);

  if (fs.statSync(resolved).isFile()) return [resolved];

  return fs
    .readdirSync(resolved, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? collectFiles(path.join(resolved, entry.name))
        : [path.join(resolved, entry.name)],
    )
    .filter((file) => /\.(?:tsx?)$/.test(file));
}

if (import.meta.main) {
  const roots = process.argv.slice(2);
  const files = roots.length ? roots.flatMap(collectFiles) : collectFiles("src/prompta/ui");
  let violationCount = 0;

  for (const file of files) {
    const violations = findDomRebuildViolations(fs.readFileSync(file, "utf8"), file);
    violationCount += violations.length;

    for (const violation of violations) {
      console.error(
        violation.file + ":" + violation.line + ":" + violation.column + " " + violation.message,
      );
    }
  }

  if (violationCount) {
    console.error(
      "Found " +
        violationCount +
        " forbidden DOM rebuild" +
        (violationCount === 1 ? "" : "s") +
        ".",
    );
    process.exitCode = 1;
  }
}
