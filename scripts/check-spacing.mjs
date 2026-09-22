import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import ts from "typescript";

const roots = process.argv.slice(2).filter((arg) => arg !== "--fix");
const shouldFix = process.argv.includes("--fix");
const files = roots.length ? roots.flatMap(collectFiles) : collectFiles("src/prompta/ui");
let violations = 0;

for (const file of files) {
  const source = fs.readFileSync(file, "utf8");
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const insertions = [];

  visitStatementLists(sourceFile, sourceFile.statements, sourceFile);

  if (!insertions.length) continue;
  violations += insertions.length;

  if (shouldFix) {
    let next = source;
    for (const position of insertions.sort((left, right) => right - left)) {
      next = `${next.slice(0, position)}\n${next.slice(position)}`;
    }
    fs.writeFileSync(file, next);
    console.log(`Fixed ${insertions.length} spacing violation(s) in ${file}`);
  } else {
    console.error(`${file}: ${insertions.length} spacing violation(s)`);
  }

  function visitStatementLists(parent, statements, root) {
    const statementArray = Array.from(statements);
    for (let index = 0; index < statementArray.length; index += 1) {
      const statement = statementArray[index];
      const previous = statementArray[index - 1];
      if (previous && needsBlankLine(previous, statement, parent, root)) {
        const lineBefore = root.getLineAndCharacterOfPosition(previous.end).line;
        const lineAt = root.getLineAndCharacterOfPosition(statement.getStart(root)).line;
        if (lineAt - lineBefore < 2) insertions.push(statement.getFullStart());
      }
      visitNestedStatementLists(statement, root);
    }
  }

  function visitNestedStatementLists(node, root) {
    node.forEachChild((child) => {
      if (ts.isBlock(child)) visitStatementLists(child, child.statements, root);
      else if (ts.isCaseBlock(child)) {
        for (const clause of child.clauses) {
          visitStatementLists(clause, clause.statements, root);
        }
      } else {
        visitNestedStatementLists(child, root);
      }
    });
  }
}

if (violations && !shouldFix) process.exitCode = 1;

function needsBlankLine(previous, current, parent, sourceFile) {
  if (ts.isEmptyStatement(current) || ts.isEmptyStatement(previous)) return false;

  const previousIsImport = ts.isImportDeclaration(previous) || ts.isImportEqualsDeclaration(previous);
  const currentIsImport = ts.isImportDeclaration(current) || ts.isImportEqualsDeclaration(current);
  if (previousIsImport || currentIsImport) return false;

  if (isDeclaration(previous) && isDeclaration(current)) return false;
  if (ts.isFunctionDeclaration(previous) || ts.isClassDeclaration(previous)) return true;
  if (ts.isFunctionDeclaration(current) || ts.isClassDeclaration(current)) return true;

  if (isControlFlowBoundary(previous) || isControlFlowBoundary(current)) return true;

  // Keep adjacent statements in a compact callback body compact when they are
  // part of a fluent/imperative chain. The stronger boundaries above still
  // separate setup, branching, and cleanup phases.
  if (parent && ts.isBlock(parent) && isSimpleExpression(previous) && isSimpleExpression(current)) {
    return hasCommentBetween(previous, current, sourceFile);
  }

  return false;
}

function isDeclaration(statement) {
  return ts.isVariableStatement(statement) || ts.isFunctionDeclaration(statement) || ts.isClassDeclaration(statement);
}

function isControlFlowBoundary(statement) {
  return (
    ts.isIfStatement(statement) ||
    ts.isForStatement(statement) ||
    ts.isForInStatement(statement) ||
    ts.isForOfStatement(statement) ||
    ts.isWhileStatement(statement) ||
    ts.isDoStatement(statement) ||
    ts.isSwitchStatement(statement) ||
    ts.isTryStatement(statement) ||
    ts.isReturnStatement(statement) ||
    ts.isThrowStatement(statement)
  );
}

function isSimpleExpression(statement) {
  return ts.isExpressionStatement(statement) || ts.isVariableStatement(statement);
}

function hasCommentBetween(previous, current, sourceFile) {
  const ranges = ts.getLeadingCommentRanges(sourceFile.getFullText(), current.getFullStart()) || [];
  return ranges.some((range) => range.pos >= previous.end);
}

function collectFiles(target) {
  const resolved = path.resolve(target);
  if (fs.statSync(resolved).isFile()) return [resolved];
  return fs
    .readdirSync(resolved, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory() ? collectFiles(path.join(resolved, entry.name)) : [path.join(resolved, entry.name)],
    )
    .filter((file) => /\.(?:[cm]?js|tsx?)$/.test(file));
}
