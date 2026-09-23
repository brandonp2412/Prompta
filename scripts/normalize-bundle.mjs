import fs from "node:fs";
import process from "node:process";

const files = process.argv.slice(2);

if (!files.length) throw new Error("Expected at least one generated bundle path.");

for (const file of files) {
  const source = fs.readFileSync(file, "utf8");
  const normalized = source.replace(/[ \t]+$/gm, "");

  if (normalized !== source) fs.writeFileSync(file, normalized);
}
