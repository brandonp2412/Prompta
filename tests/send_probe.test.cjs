const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const vm = require('node:vm');
const arm = readFileSync('src/browser_scripts/arm_page_send_probe.js', 'utf8');
const clear = readFileSync('src/browser_scripts/clear_page_send_probe.js', 'utf8');

function harness(parts, status = 200) {
  let cancelled = 0;
  let reads = 0;
  let resolvePending;
  const reader = {
    async read() {
      reads++;
      if (parts.length) return {value: new TextEncoder().encode(parts.shift()), done: false};
      return new Promise(resolve => { resolvePending = resolve; });
    },
    cancel() {
      cancelled++;
      resolvePending?.({done: true});
      return Promise.resolve();
    },
  };
  const response = {status, ok: status < 400, clone: () => ({body: {getReader: () => reader}})};
  const original = async () => response;
  const context = vm.createContext({
    window: {fetch: original}, location: new URL('https://chatgpt.com'),
    URL, Request, TextDecoder, setTimeout, clearTimeout,
  });
  vm.runInContext(arm, context);
  return {
    context, response, original,
    get cancelled() { return cancelled; },
    get reads() { return reads; },
    get probe() { return context.window.__promptaSendProbe; },
    send: (id = 'sent-id', url = '/backend-api/conversation') => context.window.fetch(url, {
      method: 'POST', body: JSON.stringify({messages: [{id}], parent_message_id: 'parent'}),
    }),
    clear: () => vm.runInContext(clear, context),
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('SSE confirmation accepts whitespace, CRLF and arbitrary byte boundaries', async () => {
  const event = 'data: ' + JSON.stringify({
    type: 'input_message', message: {id: 'sent-id'}, conversation_id: 'chat-id',
  }, null, 0).replaceAll(':', ': ') + '\r\n\r\n';
  const h = harness([...event]);
  assert.equal(await h.send(), h.response);
  await settle();
  assert.equal(h.probe.committed, true);
  assert.equal(h.probe.conversation_id, 'chat-id');
  assert.equal(h.cancelled, 1);
});

test('unrelated events and quoted text cannot manufacture acceptance', async () => {
  const h = harness([
    'data: {"type":"input_message","id":"other-id"}\n\n',
    'data: {"type":"other","id":"sent-id"}\n\n',
    'data: {"text":"\\"type\\":\\"input_message\\" \\"id\\":\\"sent-id\\""}\n\n',
  ]);
  await h.send();
  await settle();
  assert.equal(h.probe.committed, false);
  h.clear();
});

test('byte budget cancels probe without consuming or replacing original response', async () => {
  const h = harness(['x'.repeat(65536)]);
  assert.equal(await h.send(), h.response);
  await settle();
  assert.equal(h.cancelled, 1);
  assert.equal(h.reads, 1);
});

test('clear and rearm cancel a stalled stream and restore fetch', async () => {
  const h = harness([]);
  await h.send();
  await settle();
  vm.runInContext(arm, h.context);
  assert.equal(h.cancelled, 1);
  h.clear();
  assert.equal(h.context.window.fetch, h.original);
  assert.equal(h.context.window.__promptaSendProbe, undefined);
});

test('only first same-origin send belongs to probe and errors are not acceptance', async () => {
  const h = harness([], 429);
  await h.send('foreign', 'https://example.com/backend-api/conversation');
  assert.equal(h.probe.message_id, '');
  await h.send();
  await h.send('other-id');
  assert.equal(h.probe.message_id, 'sent-id');
  assert.equal(h.probe.response_status, 429);
  assert.equal(h.probe.committed, false);
  assert.equal(h.reads, 0);
  h.clear();
});

test('timeout cancels a stalled probe without claiming acceptance', async () => {
  const h = harness([]);
  let expire;
  h.context.setTimeout = callback => { expire = callback; return 0; };
  await h.send();
  await settle();
  expire();
  assert.equal(h.cancelled, 1);
  assert.equal(h.probe.committed, false);
  h.clear();
});

test('Request bodies are captured before examining confirmation', async () => {
  const h = harness(['data: {"type":"input_message","id":"sent-id"}\n\n']);
  await h.context.window.fetch(new Request('https://chatgpt.com/backend-api/f/conversation', {
    method: 'POST', body: JSON.stringify({messages: [{id: 'sent-id'}]}),
  }));
  for (let i = 0; i < 20 && !h.probe.committed; i++) await settle();
  assert.equal(h.probe.committed, true);
  h.clear();
});
