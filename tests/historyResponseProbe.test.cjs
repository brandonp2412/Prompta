const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const serializer = fs.readFileSync("src/browser_scripts/markdown_from_dom.js", "utf8");
const raw = fs.readFileSync("src/browser_scripts/historical_response_probe.js", "utf8")
  .replace("/* PROMPTA_MARKDOWN_FROM_DOM */", serializer);
for (const forbidden of [/fetch\s*\(/, /XMLHttpRequest/, /backend-api/, /window\.open\s*\(/, /setInterval\s*\(/]) {
  assert.ok(!forbidden.test(raw), "history probe must stay DOM-only");
}
const id = "12345678-1234-4123-8123-123456789abc";
const prompt = "Original prompt";
const source = raw.replace("__CONVERSATION__", JSON.stringify(id))
  .replace("__ORIGINAL_PROMPT__", JSON.stringify(prompt));
let responseText = "Recovered answer";
let generating = false;
let hiddenStop = false;
let copyReady = true;
let alertText = "";
let route = "/c/" + id;
const visible = (node) => ({
  ...node, isConnected: true, getClientRects: () => [{}],
});
const user = visible({ innerText: prompt });
const root = visible({ get innerText() { return responseText; }, parentElement: null });
const toolCard = visible({
  parentElement: null, closest: () => null, matches: () => true,
  getAttribute: (name) => ({
    'aria-label': 'Used Nox Python', 'data-state': 'completed',
  })[name] || '',
  querySelector: () => null,
});
const turn = {
  querySelectorAll: (selector) => selector.includes('copy-turn') ?
    (copyReady ? [visible({})] : []) : [toolCard],
  querySelector: () => null,
};
const assistant = visible({
  getAttribute: (name) => ({
    "data-message-id": "",
    "data-content-search-unit-key": "unit:assistant",
    "data-content-search-message-ids": "87654321-4321-4321-8321-123456789abc",
  })[name] || "",
  querySelectorAll: () => [root],
  closest: () => turn,
});
const main = {
  querySelectorAll: (selector) => selector.includes('role="user"') ? [user] : [assistant],
};
const context = {
  location: { origin: "https://chatgpt.com", get pathname() { return route; } },
  document: {
    querySelectorAll: (selector) => selector.includes('stop-button') ?
      (generating ? [visible({})] : hiddenStop ? [{ isConnected: true, getClientRects: () => [] }] : []) :
      alertText ? [visible({ textContent: alertText })] : [],
    querySelector: (selector) => selector === "main" ? main : generating ? {} : null,
  },
  getComputedStyle: () => ({ visibility: "visible" }),
};
vm.createContext(context);
const probe = () => vm.runInContext(source, context);
let result = probe();
assert.equal(result.verified, true);
assert.equal(result.text, responseText);
assert.equal(result.complete, true);
assert.equal(result.tool_calls.length, 1);
assert.equal(result.tool_calls[0].action, 'Used Nox Python');
assert.equal(result.pathname, "/c/" + id);
assert.equal(result.branch_message_id, "87654321-4321-4321-8321-123456789abc");

generating = true;
assert.equal(probe().complete, false, "generating response is never final");
generating = false;
hiddenStop = true;
assert.equal(probe().complete, true, 'hidden stop does not block completion');
hiddenStop = false;
copyReady = false;
assert.equal(probe().complete, false, "missing final-copy action is not completion");
copyReady = true;
user.innerText = "Unrelated chat";
result = probe();
assert.equal(result.ambiguous, true);
assert.equal(result.text, "", "never capture from a mismatched user prompt");
user.innerText = prompt;
alertText = "Too many requests";
assert.equal(probe().rate_limited, true);
alertText = "";
route = "/c/different";
assert.equal(probe().verified, false);
console.log("historical response probe passes exact-branch, completion and rate-limit gates");
