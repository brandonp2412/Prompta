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
  const statements = sourceFile.statements.filter(
    (statement) => !ts.isImportDeclaration(statement) && !ts.isImportEqualsDeclaration(statement),
  );

  const insertions = [];
  for (const statement of statements) {
    const previous = statements[statements.indexOf(statement) - 1];
    const firstNonImport = statements[0] === statement;
    const importStatements = sourceFile.statements.filter(
      (candidate) => ts.isImportDeclaration(candidate) || ts.isImportEqualsDeclaration(candidate),
    );
    const previousImport = importStatements.at(-1);
    const boundary = firstNonImport && previousImport ? previousImport : previous;
    if (!boundary) continue;

    const boundaryLine = sourceFile.getLineAndCharacterOfPosition(boundary.end).line;
    const statementLine = sourceFile.getLineAndCharacterOfPosition(statement.getStart(sourceFile)).line;
    if (statementLine - boundaryLine < 2) {
      insertions.push(statement.getFullStart());
    }
  }

  if (!insertions.length) continue;
  violations += insertions.length;

  if (shouldFix) {
    let next = source;
    for (const position of insertions.toReversed()) {
      next = `${next.slice(0, position)}\n${next.slice(position)}`;
    }
    fs.writeFileSync(file, next);
    console.log(`Fixed ${insertions.length} top-level spacing violation(s) in ${file}`);
  } else {
    console.error(`${file}: ${insertions.length} top-level declaration(s) need a blank line before them`);
  }
}

if (violations && !shouldFix) process.exitCode = 1;

function collectFiles(target) {
  const resolved = path.resolve(target);
  if (fs.statSync(resolved).isFile()) return [resolved];
  return fs
    .readdirSync(resolved, { withFileTypes: true })
    .flatMap((entry) => (entry.isDirectory() ? collectFiles(path.join(resolved, entry.name)) : [path.join(resolved, entry.name)]))
    .filter((file) => /\.(?:[cm]?js|tsx?)$/.test(file));
}
