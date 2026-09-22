import { describe, expect, test } from "bun:test";

import { findDomRebuildViolations } from "./check-dom-rebuilds.mjs";

function messages(source) {
  return findDomRebuildViolations(source).map((violation) => violation.message);
}

describe("DOM rebuild lint", () => {
  test("allows innerHTML on detached templates and application elements", () => {
    expect(
      messages('const template = document.createElement("template"); template.innerHTML = html;'),
    ).toEqual([]);
    expect(messages("app.innerHTML = renderApp(state);")).toEqual([]);
  });

  test("rejects document-shell innerHTML assignments", () => {
    expect(
      messages(
        "document.innerHTML = html; document.body.innerHTML = html; document.documentElement.innerHTML = html;",
      ),
    ).toHaveLength(3);
    expect(messages('document["body"].innerHTML = html;')).toHaveLength(1);
    expect(messages("app.innerHTML = html;")).toEqual([]);
  });

  test("rejects outerHTML assignments anywhere", () => {
    expect(messages("panel.outerHTML = html; document.body.outerHTML = html;")).toHaveLength(2);
  });

  test("rejects document-shell replaceChildren and document.write", () => {
    expect(
      messages(
        "document.replaceChildren(next); document.body.replaceChildren(next); panel.replaceChildren(next); document.write(html);",
      ),
    ).toHaveLength(3);
  });

  test("allows incremental DOM mutation", () => {
    expect(
      messages("panel.append(next); current.replaceWith(next); panel.insertBefore(next, current);"),
    ).toEqual([]);
  });
});
