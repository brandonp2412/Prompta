const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("src/browser_scripts/passive_response_observer.js", "utf8");
const readSource = fs.readFileSync("src/browser_scripts/passive_response_read.js", "utf8");
for (const script of [source, readSource]) {
  for (const forbidden of [/fetch\s*\(/, /XMLHttpRequest/, /backend-api/, /\.location\s*=/, /window\.open\s*\(/, /setInterval\s*\(/]) {
    assert.ok(!forbidden.test(script), "unexpected active browser operation: " + forbidden);
  }
}
const nodes = [];
let hasStop = true;
let time = 1000;
let callback;
const markdown = (text) => ({
  innerText: text,
  isConnected: true,
  getClientRects: () => [{}],
  parentElement: null,
});
const makeMessage = (id, text, copy = false) => {
  const region = markdown(text);
  const turn = {
    querySelectorAll: (selector) => selector.includes("copy-turn") ? (copy ? [region] : []) : [],
    querySelector: () => null,
  };
  return {
    isConnected: true,
    getClientRects: () => [{}],
    getAttribute: (name) => name === "data-message-id" ? id : "",
    querySelectorAll: (selector) => selector.includes(".markdown") ? [region] : [],
    closest: () => turn,
  };
};
const main = {
  querySelectorAll: () => nodes,
};
const pushed = [];
const context = {
  window: { __promptaPassiveUpdate: (snapshot) => pushed.push(snapshot) },
  document: {
    querySelector: (selector) => selector === "main" ? main : hasStop ? {} : null,
  },
  getComputedStyle: () => ({ visibility: "visible" }),
  MutationObserver: class {
    constructor(fn) { callback = fn; }
    observe() {}
    disconnect() {}
  },
  setTimeout: () => 1,
  clearTimeout: () => {},
  Date: class { static now() { return time; } },
};
vm.createContext(context);
assert.equal(vm.runInContext(source, context), true);
assert.equal(vm.runInContext(readSource, context).text, "");
nodes.push(makeMessage("new-one", "Answer"));
callback();
let snap = vm.runInContext(readSource, context);
assert.equal(snap.message_id, "new-one");
assert.equal(snap.text, "Answer");
assert.equal(snap.complete, false);
hasStop = false;
nodes[0] = makeMessage("new-one", "Answer", true);
time += 1000;
snap = vm.runInContext(readSource, context);
assert.equal(snap.complete, true);
assert.equal(pushed.at(-1).complete, true);
assert.equal(pushed.at(-1).text, "Answer");
nodes.push(makeMessage("other-branch", "Wrong branch", true));
snap = vm.runInContext(readSource, context);
assert.equal(snap.ambiguous, true);
assert.equal(snap.text, "");
console.log("Passive DOM observer: offline checks passed");
