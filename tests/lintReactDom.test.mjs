
import assert from "node:assert/strict";
import { test } from "node:test";
import { lintReactDom } from "../scripts/lint-react-dom.mjs";

test("allows keyed React lists, signals and callback refs", () => {
  const code = 'const list = items.map(item => <span key={item.id} ref={ref}>{item.name}</span>);';
  assert.deepEqual(lintReactDom(code), []);
});

test("rejects raw HTML replacement", () => {
  const errors = lintReactDom('const view = <div dangerouslySetInnerHTML={{__html: response}} />;');
  assert.equal(errors.length, 1);
  assert.match(errors[0], /dangerouslySetInnerHTML/);
});

test("rejects DOM replacement while allowing the single React root lookup", () => {
  assert.deepEqual(lintReactDom('const app = document.querySelector<HTMLElement>("#app");', "src/ui/main.tsx"), []);
  const errors = lintReactDom('document.body.replaceChildren(); element["outerHTML"] = html;');
  assert.equal(errors.length, 2);
  assert.match(errors.join("\n"), /replaceChildren/);
  assert.match(errors.join("\n"), /outerHTML/);
  assert.equal(lintReactDom('document.querySelector(".elsewhere")', "src/ui/main.tsx").length, 1);
});

test("rejects JSX module DOM replacement and manual queries", () => {
  const errors = lintReactDom('document.querySelector("#app")?.replaceChildren(); element["innerHTML"] = markup;');
  assert.equal(errors.length, 3);
  assert.match(errors.join("\n"), /querySelector/);
  assert.match(errors.join("\n"), /replaceChildren/);
  assert.match(errors.join("\n"), /innerHTML/);
});
