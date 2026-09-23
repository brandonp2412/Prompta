import { expect, test } from "bun:test";

function cssBraceDepth(source: string) {
  let depth = 0;
  let quote = "";
  let inComment = false;
  let escaped = false;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";

    if (inComment) {
      if (char === "*" && next === "/") {
        inComment = false;
        index += 1;
      }
      continue;
    }

    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = "";
      }
      continue;
    }

    if (char === "/" && next === "*") {
      inComment = true;
      index += 1;
    } else if (char === '"' || char === "'") {
      quote = char;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth < 0) return depth;
    }
  }

  return depth;
}

test("app stylesheet keeps balanced CSS blocks", async () => {
  const css = await Bun.file(new URL("../static/app.css", import.meta.url)).text();

  expect(cssBraceDepth(css)).toBe(0);
});

test("offscreen rendering avoids variable-height conversation rows", async () => {
  const css = await Bun.file(new URL("../static/app.css", import.meta.url)).text();

  expect(css).not.toMatch(/\.message \{[^}]*content-visibility: auto;/s);
  expect(css).toMatch(
    /\.chat-item \{[^}]*content-visibility: auto;[^}]*contain-intrinsic-size: auto 66px;/s,
  );
  expect(css).not.toMatch(/\.code-block \{[^}]*content-visibility: auto;/s);
  expect(css).toMatch(
    /\.changelog-entry \{[^}]*content-visibility: auto;[^}]*contain-intrinsic-size: auto 44px;/s,
  );
  expect(css).toMatch(
    /\.job-row \{[^}]*content-visibility: auto;[^}]*contain-intrinsic-size: auto 150px;/s,
  );
});
