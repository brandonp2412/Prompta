const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const isFocused = eval(fs.readFileSync('src/browser_scripts/composer_has_focus.js', 'utf8'));
const node = (parentElement = null) => ({parentElement, getRootNode: () => ({host: null})});
test('direct editor focus succeeds', () => {
  const editor = node(); global.document = {activeElement: editor};
  assert.equal(isFocused(editor), true);
});
test('focus inside editor descendant succeeds', () => {
  const editor = node(); global.document = {activeElement: node(editor)};
  assert.equal(isFocused(editor), true);
});
test('nested shadow focus succeeds', () => {
  const editor = node(); const shadowHost = node(editor);
  const inside = node(); inside.getRootNode = () => ({host: shadowHost});
  shadowHost.shadowRoot = {activeElement: inside};
  global.document = {activeElement: shadowHost};
  assert.equal(isFocused(editor), true);
});
test('stolen focus in unrelated popup fails closed', () => {
  const editor = node(); global.document = {activeElement: node()};
  assert.equal(isFocused(editor), false);
});
test('shadow root focus in unrelated popup fails closed', () => {
  const editor = node(); const popup = node();
  popup.shadowRoot = {activeElement: node()};
  global.document = {activeElement: popup};
  assert.equal(isFocused(editor), false);
});
test('missing focused element fails closed', () => {
  global.document = {activeElement: null}; assert.equal(isFocused(node()), false);
});
