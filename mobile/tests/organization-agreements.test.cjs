const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise(setImmediate); };
function load(file, requireModule) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, file), 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require: requireModule }); return module.exports;
}
function harness(client, pages) {
  const values = [], effects = []; let slot = 0, tree;
  const react = { useState(initial) { const i = slot++; if (!(i in values)) values[i] = initial; return [values[i], next => { values[i] = typeof next === 'function' ? next(values[i]) : next; }]; },
    useRef(initial) { const i = slot++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
    useCallback(fn, deps) { const i = slot++; if (!values[i] || deps.some((v, j) => v !== values[i].deps[j])) values[i] = { fn, deps }; return values[i].fn; } };
  const focus = fn => { const i = slot++; if (values[i]?.fn !== fn) { values[i]?.cleanup?.(); const state = values[i] = { fn }; effects.push(() => { state.cleanup = fn(); }); } };
  const jsx = (type, props) => ({ type, props: props || {} });
  const agreementClient = load('../src/organizations/agreements.ts', () => client);
  const module = load('../app/organization-agreements.tsx', name => {
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react-native') return Object.fromEntries(['ActivityIndicator', 'Button', 'Switch', 'Text', 'TextInput', 'View'].map(x => [x, x]));
    if (name === 'expo-router') return { Link: 'Link', Stack: { Screen: 'Screen' }, useFocusEffect: focus, useLocalSearchParams: () => ({}) };
    if (name.endsWith('/components/Page')) return { Page: 'Page', ui: { card: {} } };
    if (name.endsWith('/organizations/rosters')) return { rosterPages: pages };
    if (name.endsWith('/organizations/agreements')) return agreementClient;
    if (name.endsWith('/api/client')) return client;
    throw Error(name);
  });
  function nodes(node) { if (!arguments.length) node = tree; if (Array.isArray(node)) return node.flatMap(n => nodes(n)); if (!node || typeof node !== 'object') return [];
    if (typeof node.type === 'function' && node.type.name === 'TermsFields') return nodes(node.type(node.props));
    return [node, ...nodes(node.props?.children || [])]; }
  return { module, nodes, render(component, props) { slot = 0; tree = component(props); while (effects.length) effects.shift()(); } };
}
const row = () => ({ id: 7, title: 'Sponsorship', kind: 'SPONSORSHIP', status: 'PENDING', terms: '<script>Plain agreed terms</script>', revision: 3, end_round: 0,
  organization_name: 'Academy', talent_name: 'Talent', roster_snapshot: { roster: 'First team', tag: 'Player' }, consents: [], actions: [{ action: 'ACCEPT', party: 'TALENT' }], amount: '50.00', currency: 'GHS', can_revise: false });

test('mobile requires explicit consent and sends the displayed revision and acting party', async () => {
  const calls = [], h = harness({ apiRequest: async (url, options) => { calls.push({ url, options }); } }, async () => []);
  const props = { row: row(), working: false, mutate: async operation => operation() };
  const render = () => h.render(h.module.AgreementCard, props); render();
  let button = h.nodes().find(n => n.props.title === 'Accept terms — talent'); assert.equal(button.props.disabled, true);
  h.nodes().find(n => n.type === 'Switch').props.onValueChange(true); render();
  button = h.nodes().find(n => n.props.title === 'Accept terms — talent'); assert.equal(button.props.disabled, false);
  button.props.onPress(); await flush();
  assert.equal(calls[0].url, 'organizations/agreements/7/');
  assert.equal(calls[0].options.body.consent, true); assert.equal(calls[0].options.body.expected_revision, 3); assert.equal(calls[0].options.body.party, 'TALENT');
});

test('mobile mutual-ending request requires consent plus a reason and binds the ending round', async () => {
  const calls = [], h = harness({ apiRequest: async (url, options) => { calls.push(options); } }, async () => []);
  const props = { row: { ...row(), status: 'ACTIVE', end_round: 2, actions: [{ action: 'REQUEST_END', party: 'TALENT' }] }, working: false, mutate: async op => op() };
  const render = () => h.render(h.module.AgreementCard, props); render();
  h.nodes().find(n => n.type === 'Switch').props.onValueChange(true); render();
  assert.equal(h.nodes().find(n => n.props.title === 'Request mutual ending — talent').props.disabled, true);
  h.nodes().find(n => n.props.accessibilityLabel === 'Agreement decision reason').props.onChangeText('Campaign completed'); render();
  const button = h.nodes().find(n => n.props.title === 'Request mutual ending — talent'); assert.equal(button.props.disabled, false);
  button.props.onPress(); await flush(); assert.equal(calls[0].body.expected_end_round, 2); assert.equal(calls[0].body.reason, 'Campaign completed');
});

test('mobile saves a draft without automatically submitting or giving consent', async () => {
  const calls = [], h = harness({ apiRequest: async (url, options) => { calls.push({ url, options }); } }, async url => url.includes('roster-choices') ? [{ id: 5, organization_id: 1, organization_name: 'Academy', name: 'Talent', tag: 'Player', roster: 'First team' }] : []);
  const render = () => h.render(h.module.default); render(); await flush(); render();
  h.nodes().find(n => n.props.title === 'Academy · Talent · Player').props.onPress(); render();
  for (const [label, value] of [['Title', 'Contract draft'], ['Terms', 'Exact compensation and obligations']]) {
    h.nodes().find(n => n.props.accessibilityLabel === label).props.onChangeText(value); render();
  }
  const button = h.nodes().find(n => n.props.title === 'Save draft'); assert.equal(button.props.disabled, false);
  button.props.onPress(); await flush(); render();
  assert.equal(calls.length, 1); assert.equal(calls[0].options.body.roster_entry_id, 5); assert.equal(calls[0].options.body.consent, undefined);
  assert.equal(calls[0].options.body.kind, 'CONTRACT');
});

test('mobile revisions use PATCH with expected revision and history shows the old exact terms', async () => {
  const calls = [], h = harness({ apiRequest: async (url, options) => { calls.push(options); } }, async () => [{ id: 1, action: 'REVISED', actor_name: 'Owner', revision: 2, created_at: '2026-10-21T12:00:00Z', reason: 'Updated scope', snapshot: { terms: 'Historical exact terms' } }]);
  const props = { row: { ...row(), status: 'DRAFT', can_revise: true, actions: [] }, working: false, mutate: async op => op() };
  const render = () => h.render(h.module.AgreementCard, props); render();
  h.nodes().find(n => n.props.title === 'Revise terms (requires fresh consent)').props.onPress(); render();
  h.nodes().find(n => n.props.accessibilityLabel === 'Terms').props.onChangeText('Revised exact terms'); render();
  h.nodes().find(n => n.props.title === 'Save revised draft').props.onPress(); await flush();
  assert.equal(calls[0].method, 'PATCH'); assert.equal(calls[0].body.expected_revision, 3); assert.equal(calls[0].body.terms, 'Revised exact terms');
  h.nodes().find(n => n.props.title === 'View agreement history').props.onPress(); await flush(); render();
  assert.ok(JSON.stringify(h.nodes()).includes('Historical exact terms'));
});
