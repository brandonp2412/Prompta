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
    documentElement: {},
    querySelector: (selector) => selector === "main" ? main : hasStop ? {} : null,
    querySelectorAll: () => nodes,
  },
  getComputedStyle: () => ({ visibility: "visible" }),
  location: { pathname: "/c/test" },
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
nodes[0] = makeMessage("other-branch", "Wrong branch", true);
snap = vm.runInContext(readSource, context);
assert.equal(snap.ambiguous, true);
assert.equal(snap.text, "");
assert.equal(pushed.at(-1).ambiguous, true);
nodes[0] = makeMessage("new-one", "Answer", true);
snap = vm.runInContext(readSource, context);
assert.equal(snap.ambiguous, true, "a branch rollover stays invalid even if the old id returns");
nodes.push(makeMessage("another-branch", "Other", true));
assert.equal(vm.runInContext(readSource, context).ambiguous, true);
// A route remount must not blind the observer; modern units can list many assistant IDs.
let modernNodes = [makeMessage("baseline", "Earlier answer", true)];
let modernMain = { querySelectorAll: () => modernNodes };
let modernTime = 1000;
let modernCopy = false;
let observedRoot = null;
const modernRoot = {};
const modernResponse = {
  isConnected: true,
  getClientRects: () => [{}],
  getAttribute: (name) => ({
    "data-message-id": "",
    "data-chatgpt-search-unit-key": "new-turn:assistant",
    "data-chatgpt-search-message-ids": "id1 id2 id3 id4 id5",
  })[name] || "",
  querySelectorAll: (selector) => selector.includes(".markdown") ? [markdown("Actual answer")] :
    selector.includes("copy-turn") ? (modernCopy ? [markdown("")] : []) : [],
  querySelector: () => null,
  closest: () => null,
};
const modernContext = {
  window: { __promptaPassiveUpdate: () => {} },
  document: {
    documentElement: modernRoot,
    querySelector: (selector) => selector === "main" ? modernMain : null,
    querySelectorAll: () => modernNodes,
  },
  getComputedStyle: () => ({ visibility: "visible" }),
  location: { pathname: "/c/test" },
  MutationObserver: class {
    constructor() {}
    observe(target) { observedRoot = target; }
    disconnect() {}
  },
  setTimeout: () => 1,
  clearTimeout: () => {},
  Date: class { static now() { return modernTime; } },
};
vm.createContext(modernContext);
assert.equal(vm.runInContext(source, modernContext), true);
assert.equal(observedRoot, modernRoot);
modernNodes = [makeMessage("baseline", "Earlier answer", true), modernResponse];
modernMain = { querySelectorAll: () => modernNodes }; // React replaced <main> during routing.
let modernSnapshot = vm.runInContext(readSource, modernContext);
assert.equal(modernSnapshot.message_id, "new-turn:assistant");
assert.equal(modernSnapshot.text, "Actual answer");
assert.equal(modernSnapshot.complete, false);
modernCopy = true;
modernTime += 1000;
modernSnapshot = vm.runInContext(readSource, modernContext);
assert.equal(modernSnapshot.complete, true);
console.log("Passive DOM observer: offline checks passed");
