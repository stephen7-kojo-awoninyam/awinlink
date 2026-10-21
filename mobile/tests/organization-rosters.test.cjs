const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };
function load(file, requireModule) {
  const source = fs.readFileSync(path.resolve(__dirname, file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: requireModule });
  return module.exports;
}

function hookHarness() {
  const values = []; let slot = 0, tree; const effects = [];
  const react = {
    useState(initial) { const i = slot++; if (!(i in values)) values[i] = initial; return [values[i], next => { values[i] = typeof next === 'function' ? next(values[i]) : next; }]; },
    useRef(initial) { const i = slot++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
    useCallback(fn, deps) { const i = slot++; const old = values[i]; if (!old || deps.some((v, j) => old.deps[j] !== v)) values[i] = { fn, deps }; return values[i].fn; },
  };
  const focus = fn => { const i = slot++; if (values[i]?.fn !== fn) { values[i]?.cleanup?.(); const value = values[i] = { fn }; effects.push(() => { value.cleanup = fn(); }); } };
  const jsx = (type, props) => ({ type, props: props || {} });
  const common = name => {
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react-native') return Object.fromEntries(['ActivityIndicator', 'Button', 'Text', 'TextInput', 'View'].map(x => [x, x]));
    if (name === 'expo-router') return { Link: 'Link', Stack: { Screen: 'Screen' }, useFocusEffect: focus };
    if (name.endsWith('/components/Page')) return { Page: 'Page', ui: { card: {} } };
  };
  function collect(node) { if (Array.isArray(node)) return node.flatMap(collect); if (!node || typeof node !== 'object') return []; return [node, ...collect(node.props?.children)]; }
  return { common, render(Component, props) { slot = 0; tree = Component(props); while (effects.length) effects.shift()(); }, nodes: () => collect(tree) };
}

test('mobile roster client paginates through authenticated relative paths and submits explicit transitions', async () => {
  const calls = [];
  const client = load('../src/organizations/rosters.ts', () => ({ apiRequest: async (url, options) => {
    calls.push({ url, options }); return { results: [{ id: calls.length }], next: calls.length === 1 ? 'https://untrusted.example/next' : null };
  } }));
  const rows = await client.rosterPages('organizations/7/roster/');
  assert.equal(rows.length, 2);
  assert.deepEqual(calls.map(c => c.url), ['organizations/7/roster/?page=1', 'organizations/7/roster/?page=2']);
  await client.updateTag(9, 'CONFIRM', '', 'Confirmed by talent');
  assert.equal(calls[2].options.method, 'POST');
  assert.equal(calls[2].options.body.action, 'CONFIRM');
  assert.equal(calls[2].options.body.reason, 'Confirmed by talent');
});

test('mobile organization workspace creates unclaimed talent entries and viewers lack add controls', async () => {
  for (const canManage of [true, false]) {
    const h = hookHarness(), calls = [];
    const screen = load('../app/organization-rosters.tsx', name => h.common(name) || (name.endsWith('/organizations/rosters') ? {
      rosterPages: async url => url.includes('workspaces') ? [{ id: 7, name: 'Academy', can_manage: canManage }] : [], updateTag: async () => {},
    } : name.endsWith('/api/client') ? { apiRequest: async (url, options) => { calls.push({ url, options }); } } : (() => { throw Error(name); })())).default;
    const render = () => h.render(screen);
    render(); await flush(); render();
    h.nodes().find(n => n.props.title === 'Academy').props.onPress(); render(); await flush(); render();
    assert.equal(h.nodes().some(n => n.props.title === 'Add talent'), canManage);
    if (canManage) {
      for (const [label, value] of [['Talent name', 'Unclaimed Player'], ['Tag', 'Player'], ['Roster', 'First team']]) {
        h.nodes().find(n => n.props.accessibilityLabel === label).props.onChangeText(value); render();
      }
      const add = h.nodes().find(n => n.props.title === 'Add talent'); assert.equal(add.props.disabled, false);
      add.props.onPress(); await flush(); render();
      assert.equal(calls[0].url, 'organizations/7/roster/');
      assert.equal(calls[0].options.body.username, ''); assert.equal(calls[0].options.body.name, 'Unclaimed Player');
    }
  }
});

test('mobile talent confirms a pending tag and removal requires a separate confirmation', async () => {
  const h = hookHarness(), calls = [];
  const Card = load('../app/organization-rosters.tsx', name => h.common(name) || (name.endsWith('/organizations/rosters') ? {
    rosterPages: async () => [{ id: 1, action: 'CONFIRM', reason: 'Agreed', created_at: '2026-10-21T12:00:00Z' }],
  } : name.endsWith('/api/client') ? {} : (() => { throw Error(name); })())).TagCard;
  const props = { entry: { id: 4, name: 'Talent', organization_name: 'Academy', tag: 'Player', status: 'PENDING', actions: ['CONFIRM', 'DECLINE', 'REMOVE'] }, working: false, act: async (...args) => calls.push(args) };
  const render = () => h.render(Card, props);
  render();
  h.nodes().find(n => n.props.accessibilityLabel === 'Action reason').props.onChangeText('Agreed'); render();
  h.nodes().find(n => n.props.title === 'Confirm affiliation').props.onPress(); await flush();
  assert.deepEqual(calls[0], [4, 'CONFIRM', '', 'Agreed']);
  h.nodes().find(n => n.props.title === 'Remove tag').props.onPress(); render();
  assert.equal(calls.length, 1);
  h.nodes().find(n => n.props.title === 'Confirm removal').props.onPress(); await flush(); render();
  assert.equal(calls[1][1], 'REMOVE');
  h.nodes().find(n => n.props.title === 'View history').props.onPress(); await flush(); render();
  assert.ok(h.nodes().some(n => n.type === 'Text' && JSON.stringify(n.props.children).includes('Agreed')));
});

test('mobile clears organization drafts and keeps personal requests after workspace access is revoked', async () => {
  const h = hookHarness(); let revoked = false;
  const Screen = load('../app/organization-rosters.tsx', name => h.common(name) || (name.endsWith('/organizations/rosters') ? {
    rosterPages: async url => url.includes('workspaces') ? (revoked ? [] : [{ id: 7, name: 'Academy', can_manage: true }, { id: 8, name: 'Club', can_manage: true }]) : url.includes('mine') ? [{ id: 9, name: 'Personal request', status: 'PENDING', actions: ['CONFIRM'] }] : [],
    updateTag: async () => {},
  } : name.endsWith('/api/client') ? {} : (() => { throw Error(name); })())).default;
  const render = () => h.render(Screen);
  render(); await flush(); render();
  h.nodes().find(n => n.props.title === 'Academy').props.onPress(); render(); await flush(); render();
  h.nodes().find(n => n.props.accessibilityLabel === 'Talent name').props.onChangeText('Private draft'); render();
  h.nodes().find(n => n.props.title === 'Club').props.onPress(); render(); await flush(); render();
  assert.equal(h.nodes().find(n => n.props.accessibilityLabel === 'Talent name').props.value, '');
  revoked = true;
  h.nodes().find(n => n.props.title === 'Refresh rosters').props.onPress(); await flush(); render(); await flush(); render();
  assert.ok(h.nodes().some(n => n.props.entry?.name === 'Personal request'));
  assert.ok(!h.nodes().some(n => n.props.title === 'Add talent'));
});

test('mobile personal requests remain usable when an organization roster read fails', async () => {
  const h = hookHarness();
  const Screen = load('../app/organization-rosters.tsx', name => h.common(name) || (name.endsWith('/organizations/rosters') ? {
    rosterPages: async url => { if (url.includes('workspaces')) return [{ id: 7, name: 'Academy', can_manage: true }]; if (url.includes('mine')) return [{ id: 9, name: 'Personal request', actions: ['CONFIRM'] }]; throw new Error('Roster access denied'); }, updateTag: async () => {},
  } : name.endsWith('/api/client') ? {} : (() => { throw Error(name); })())).default;
  const render = () => h.render(Screen);
  render(); await flush(); render();
  h.nodes().find(n => n.props.title === 'Academy').props.onPress(); render(); await flush(); render();
  assert.ok(h.nodes().some(n => n.props.entry?.name === 'Personal request'));
  assert.ok(!h.nodes().some(n => n.props.title === 'Add talent'));
  assert.ok(h.nodes().some(n => n.props.accessibilityRole === 'alert'));
});

test('roster screen belongs to the authenticated mobile navigator', () => {
  const jsx = (type, props) => ({ type, props: props || {} });
  const Root = load('../app/_layout.tsx', name => {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'expo-router') return { Stack: { Screen: 'Screen', Protected: 'Protected' } };
    if (name === 'expo-status-bar') return { StatusBar: 'StatusBar' };
    if (name.endsWith('/auth/AuthProvider')) return { AuthProvider: 'AuthProvider', useAuth: () => ({ user: { id: 1 }, isLoading: false }) };
    if (name.endsWith('/calls/IncomingCallListener')) return { IncomingCallListener: 'IncomingCallListener' };
    if (name.endsWith('/components/LoadingScreen')) return { LoadingScreen: 'LoadingScreen' };
    throw Error(name);
  }).default;
  const root = Root(); const navigation = root.props.children.find(node => typeof node.type === 'function');
  function nodes(node) { if (Array.isArray(node)) return node.flatMap(nodes); if (!node || typeof node !== 'object') return []; return [node, ...nodes(node.props?.children)]; }
  const tree = navigation.type();
  const protectedGroup = nodes(tree).find(node => node.type === 'Protected' && node.props.guard === true);
  assert.ok(nodes(protectedGroup).some(node => node.props.name === 'organization-rosters'));
  assert.ok(nodes(protectedGroup).some(node => node.props.name === 'organization-agreements'));
});

test('mobile profile badges discard late responses after switching profiles', async () => {
  const h = hookHarness(); const pending = [];
  const Badges = load('../src/organizations/Badges.tsx', name => h.common(name) || (name === './rosters' ? {
    rosterPages: url => new Promise(resolve => pending.push({ url, resolve })),
  } : (() => { throw Error(name); })())).OrganizationBadges;
  h.render(Badges, { talentId: 1 });
  h.render(Badges, { talentId: 2 });
  pending[1].resolve([{ id: 2, organization_name: 'Current Academy', tag: 'Member' }]); await flush();
  h.render(Badges, { talentId: 2 });
  pending[0].resolve([{ id: 1, organization_name: 'Previous Academy', tag: 'Member' }]); await flush();
  h.render(Badges, { talentId: 2 });
  const text = JSON.stringify(h.nodes());
  assert.ok(text.includes('Current Academy')); assert.ok(!text.includes('Previous Academy'));
});
