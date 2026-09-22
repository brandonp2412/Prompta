import { describe, expect, test } from "bun:test";

import { findDomRebuildViolations } from "./check-dom-rebuilds.mjs";

function messages(source) {
  return findDomRebuildViolations(source).map((violation) => violation.message);
}

describe("DOM rebuild lint", () => {
  test("allows innerHTML only on detached template elements", () => {
    expect(
      messages('const template = document.createElement("template"); template.innerHTML = html;'),
    ).toEqual([]);
  });

  test("rejects mounted innerHTML and outerHTML assignments", () => {
    expect(messages("panel.innerHTML = html; panel.outerHTML = html;")).toHaveLength(2);
    expect(messages('panel["innerHTML"] = html;')).toHaveLength(1);
  });

  test("does not let a template variable in another scope bypass the rule", () => {
    expect(
      messages(
        'const template = document.createElement("template"); function render(template) { template.innerHTML = html; }',
      ),
    ).toHaveLength(1);
  });

  test("rejects replaceChildren and document.write", () => {
    expect(messages("panel.replaceChildren(next); document.write(html);")).toHaveLength(2);
  });

  test("allows incremental DOM mutation", () => {
    expect(
      messages("panel.append(next); current.replaceWith(next); panel.insertBefore(next, current);"),
    ).toEqual([]);
  });
});
