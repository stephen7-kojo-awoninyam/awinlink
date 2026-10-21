const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise(setImmediate); };
function load(file, requireModule, globals = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: requireModule, FormData, URL, ...globals });
  return module.exports;
}
async function screen(role) {
  const values = [], calls = []; let slot = 0, initialized = false, tree;
  const data = { id: 7, title: 'Private service', status: role === 'talent' ? 'IN_PROGRESS' : 'SUBMITTED',
    amount: '50.00', currency: 'GHS', snapshot: { terms: 'Exact terms' }, starts_at: '2026-11-01T10:00:00Z',
    ends_at: '2026-11-01T11:00:00Z', review: null,
    capabilities: { submit: role === 'talent', complete: role !== 'talent', request_changes: role !== 'talent', message: true } };
  const jsx = (type, props) => ({ type, props: props || {} });
  const Screen = load('../app/market-bookings.tsx', name => {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react') return { useState(initial) { const index = slot++; if (!(index in values)) values[index] = initial;
      return [values[index], next => { values[index] = typeof next === 'function' ? next(values[index]) : next; }]; },
      useEffect(fn) { if (!initialized) fn(); } };
    if (name === 'react-native') return { ...Object.fromEntries(['Button', 'Switch', 'Text', 'TextInput', 'View'].map(x => [x, x])), Platform: { OS: 'web' } };
    if (name === 'expo-router') return { Link: 'Link', Redirect: 'Redirect', useLocalSearchParams: () => ({ booking: '7' }) };
    if (name === 'expo-document-picker') return { getDocumentAsync: async () => ({ canceled: true }) };
    if (name.endsWith('/marketplace/files')) return { savePrivateArtifact: async () => {} };
    if (name.endsWith('/auth/AuthProvider')) return { useAuth: () => ({ user: { id: 1 }, isLoading: false }) };
    if (name.endsWith('/components/Page')) return { Page: 'Page' };
    if (name.endsWith('/api/client')) return { apiRequest: async (url, options = {}) => {
      calls.push({ url, options });
      if (url === 'marketplace/bookings/') return { results: [{ ...data }], next: null };
      if (url.endsWith('/events/')) return { results: [{ id: 1, action: 'REQUEST_CHANGES', reason: 'Please revise', created_at: '2026-11-01T11:00:00Z' }], next: null };
      if (url.endsWith('/messages/?before=2')) return { messages: [{ id: 1, author: 1, body: 'Older' }], next_before: null };
      if (url.endsWith('/messages/')) return options.body ? { id: 3 } : { messages: [{ id: 2, author: 2, body: 'Latest' }], next_before: 2 };
      if (url.endsWith('/submissions/')) {
        if (options.body) { data.status = 'SUBMITTED'; data.capabilities.submit = false; return { id: 1 }; }
        return { results: [{ id: 1, sequence: 1, summary: 'Delivery', artifact_name: '' }], next: null };
      }
      if (url.endsWith('/reviews/')) { data.review = { rating: options.body.rating, text: options.body.text }; data.capabilities.review = false; return { id: 9 }; }
      if (options.body?.action === 'COMPLETE') { data.status = 'COMPLETED'; data.capabilities = { review: true, message: false }; }
      return { ...data, capabilities: { ...data.capabilities } };
    } };
    throw Error(name);
  }).default;
  const render = () => { slot = 0; tree = Screen(); initialized = true; };
  function collect(value) { if (Array.isArray(value)) return value.flatMap(collect); if (!value || typeof value !== 'object') return []; return [value, ...collect(value.props?.children)]; }
  const nodes = () => collect(tree);
  async function press(title) { const node = nodes().find(n => n.type === 'Button' && n.props.title === title); assert.ok(node, title); assert.equal(node.props.disabled, false); node.props.onPress(); await flush(); render(); }
  const fill = (label, value) => { nodes().find(n => n.props.accessibilityLabel === label).props.onChangeText(value); render(); };
  render(); await flush(); render();
  return { calls, nodes, press, fill, render };
}

test('mobile fulfillment prepends history and submits delivery as the talent', async () => {
  const f = await screen('talent');
  assert.ok(!f.nodes().some(n => n.props.title === 'COMPLETE'));
  await f.press('Load older messages');
  const messages = f.nodes().filter(n => n.type === 'Text').map(n => JSON.stringify(n.props.children));
  assert.ok(messages.findIndex(x => x.includes('Older')) < messages.findIndex(x => x.includes('Latest')));
  f.fill('Delivery summary', 'Verified delivery'); await f.press('Submit delivery');
  const call = f.calls.find(c => c.url.endsWith('/submissions/') && c.options.method === 'POST');
  assert.equal(call.options.body.get('summary'), 'Verified delivery');
  assert.ok(!f.nodes().some(n => n.props.title === 'Submit delivery'));
});

test('mobile buyer completes then reviews with explicit publication consent', async () => {
  const f = await screen('buyer');
  assert.ok(!f.nodes().some(n => n.props.title === 'Submit delivery'));
  await f.press('COMPLETE');
  assert.ok(!f.nodes().some(n => n.props.title === 'Send message'));
  f.fill('Rating (1-5)', '2'); f.fill('Review', 'Honest feedback');
  f.nodes().find(n => n.props.accessibilityLabel === 'Publish review').props.onValueChange(true); f.render();
  await f.press('Save review');
  const call = f.calls.find(c => c.url.endsWith('/reviews/'));
  assert.equal(call.options.body.rating, 2); assert.equal(call.options.body.publish, true);
  assert.ok(!f.nodes().some(n => n.props.title === 'Save review'));
});

test('private artifact saving asks for an Android destination and sanitizes the filename', async () => {
  const calls = [];
  const files = load('../src/marketplace/files.ts', name => name === 'react-native' ? { Platform: { OS: 'android' } } : {
    EncodingType: { Base64: 'base64' },
    StorageAccessFramework: { requestDirectoryPermissionsAsync: async () => ({ granted: true, directoryUri: 'content://chosen-folder' }),
      createFileAsync: async (...args) => { calls.push(args); return 'content://chosen-file'; } },
    writeAsStringAsync: async (...args) => calls.push(args),
  });
  await files.savePrivateArtifact({ filename: '../private.txt', content: 'YWJj' });
  assert.equal(calls[0][0], 'content://chosen-folder'); assert.equal(calls[0][1], '.._private.txt');
  assert.equal(calls[1][0], 'content://chosen-file'); assert.equal(calls[1][1], 'YWJj');
});
