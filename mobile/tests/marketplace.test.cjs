const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
function compile(file, requireModule, globals = {}) {
  const source = readFileSync(resolve(__dirname, file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: requireModule,
    URL, URLSearchParams, Headers, FormData, ...globals }, { filename: file });
  return module.exports;
}

function fixture() {
  const calls = [], state = [];
  let index = 0, initialized = false, tree;
  let room = { offer: { id: 7, terms: 'Exact terms', status: 'PENDING' },
    messages: [{ id: 51, author: 1, body: 'Latest' }], next_before: 51,
    permissions: { can_message: true, can_accept: true, can_decline: true, can_withdraw: false } };
  const api = compile('../src/api/client.ts', name => {
    assert.equal(name, 'expo-secure-store');
    return { getItemAsync: async () => 'fixture-token' };
  }, { process: { env: { EXPO_PUBLIC_API_URL: 'https://fixture.invalid' } },
    fetch: async (url, options) => {
      const path = new URL(url).pathname + new URL(url).search;
      const data = options.body === undefined ? undefined : JSON.parse(options.body);
      calls.push({ path, options, data });
      if (data !== undefined) assert.equal(typeof data, 'object', 'wire JSON must be an object, serialized once');
      let result;
      if (path.endsWith('/markets/')) result = { ecosystems: [{ id: 'SPORTS', name: 'Sports' }], subecosystems: [{ id: 1, name: 'Basketball' }] };
      else if (path.includes('/listings/')) result = data ? { id: 3 } : { results: [], next: null };
      else if (path.endsWith('/offers/')) result = data ? { id: 7 } : { results: [{ id: 7, status: room.offer.status }], next: null };
      else if (path.includes('/messages/?')) result = { messages: [{ id: 1, author: 2, body: 'Oldest' }], next_before: null };
      else if (data?.action) {
        room = { ...room, offer: { ...room.offer, status: 'ACCEPTED' }, permissions: { can_message: false, can_accept: false, can_decline: false, can_withdraw: false } };
        result = room.offer;
      } else result = room;
      return { ok: true, status: data ? 201 : 200, json: async () => result };
    },
  });
  const jsx = (type, props) => ({ type, props: props || {} });
  const Screen = compile('../app/marketplace.tsx', name => {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react') return {
      useState(initial) { const slot = index++; if (!(slot in state)) state[slot] = initial;
        return [state[slot], value => { state[slot] = typeof value === 'function' ? value(state[slot]) : value; }]; },
      useEffect(fn) { if (!initialized) fn(); },
    };
    if (name === 'react-native') return Object.fromEntries(['Button', 'Switch', 'Text', 'TextInput', 'View'].map(x => [x, x]));
    if (name === 'expo-router') return { Redirect: 'Redirect' };
    if (name.endsWith('/api/client')) return api;
    if (name.endsWith('/auth/AuthProvider')) return { useAuth: () => ({ user: { id: 1 }, isLoading: false }) };
    if (name.endsWith('/components/Page')) return { Page: 'Page' };
    throw Error(name);
  }).default;
  function render() { index = 0; tree = Screen(); initialized = true; return tree; }
  function collect(value) {
    if (Array.isArray(value)) return value.flatMap(collect);
    if (!value || typeof value !== 'object') return [];
    return [value, ...collect(value.props?.children)];
  }
  function nodes() { return collect(tree); }
  async function press(title) {
    const button = nodes().find(x => x.type === 'Button' && x.props.title === title);
    assert.ok(button, `Missing button ${title}`);
    assert.equal(button.props.disabled, false);
    button.props.onPress(); await flush(); render();
  }
  function fill(label, value) {
    const input = nodes().find(x => x.type === 'TextInput' && x.props.accessibilityLabel === label);
    assert.ok(input, label); input.props.onChangeText(value); render();
  }
  return { calls, render, nodes, press, fill, async start() { render(); await flush(); render(); } };
}

test('mobile marketplace sends object JSON for create, update, offer, message and decision', async () => {
  const f = fixture(); await f.start();
  f.fill('Title', 'Caf\u00e9 \u2713'); f.fill('Description', 'Unicode \ud83c\udfc0');
  await f.press('Save as DRAFT');
  assert.equal(f.calls.find(x => x.options.method === 'POST').data.title, 'Caf\u00e9 \u2713');
  f.fill('Listing ID (empty to create)', '3'); await f.press('Save as PAUSED');
  assert.ok(f.calls.some(x => x.options.method === 'PATCH' && x.path.endsWith('/listings/3/')));
  f.fill('Listing ID', '3'); f.fill('Exact offer terms', 'Training'); await f.press('Send offer');
  assert.ok(f.nodes().some(x => x.props.title === 'ACCEPT'));
  assert.ok(!f.nodes().some(x => x.props.title === 'WITHDRAW'));
  f.fill('Message', 'Hello \ud83d\udc4b'); await f.press('Send message');
  assert.ok(f.calls.some(x => x.data?.body === 'Hello \ud83d\udc4b'));
  const consent = f.nodes().find(x => x.props.accessibilityLabel === 'Accept offer consent');
  consent.props.onValueChange(true); f.render(); await f.press('ACCEPT');
  assert.ok(f.calls.some(x => x.data?.action === 'ACCEPT' && x.data.consent === true));
  assert.ok(!f.nodes().some(x => ['Send message', 'ACCEPT', 'DECLINE', 'WITHDRAW'].includes(x.props.title)));
  assert.ok(f.calls.every(x => x.options.headers.get('Authorization') === 'Bearer fixture-token'));
});

test('mobile history prepends older messages and removes exhausted pagination', async () => {
  const f = fixture(); await f.start(); await f.press('Send offer');
  await f.press('Load older messages');
  assert.ok(f.calls.some(x => x.path.endsWith('/deals/7/messages/?before=51')));
  const texts = f.nodes().filter(x => x.type === 'Text').map(x => JSON.stringify(x.props.children));
  assert.ok(texts.findIndex(x => x.includes('Oldest')) < texts.findIndex(x => x.includes('Latest')));
  assert.ok(!f.nodes().some(x => x.props.title === 'Load older messages'));
});
