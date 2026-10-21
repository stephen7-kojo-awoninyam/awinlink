/* Native TSX screen actions -> real JWT HTTP -> isolated PostgreSQL fixtures. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('../mobile/node_modules/typescript');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.ok(['localhost', '127.0.0.1'].includes(new URL(fixture.origin).hostname));
const pending = new Set();
const api = user => async (url, options = {}) => {
  const operation = (async () => {
    const response = await fetch(`${fixture.origin}/api/${url}`, { method: options.method || 'GET',
      headers: { Authorization: `Bearer ${fixture.tokens[user]}`, 'Content-Type': 'application/json' },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}) });
    const data = await response.json();
    if (!response.ok) throw new Error(`${response.status}: ${JSON.stringify(data)}`);
    return data;
  })();
  pending.add(operation);
  try { return await operation; } finally { pending.delete(operation); }
};
function load(file, requireModule) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'mobile', file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: requireModule });
  return module.exports;
}
function controller(user, component = 'default', props) {
  const values = [], effects = []; let slot = 0, tree;
  const react = {
    useState(initial) { const i = slot++; if (!(i in values)) values[i] = initial; return [values[i], next => { values[i] = typeof next === 'function' ? next(values[i]) : next; }]; },
    useRef(initial) { const i = slot++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
    useCallback(fn, deps) { const i = slot++; if (!values[i] || deps.some((v, j) => values[i].deps[j] !== v)) values[i] = { fn, deps }; return values[i].fn; },
  };
  const focus = fn => { const i = slot++; if (values[i]?.fn !== fn) { values[i]?.cleanup?.(); const state = values[i] = { fn }; effects.push(() => { state.cleanup = fn(); }); } };
  const jsx = (type, props) => ({ type, props: props || {} });
  const client = { apiRequest: api(user) };
  const rosters = load('src/organizations/rosters.ts', () => client);
  const Screen = load('app/organization-rosters.tsx', name => {
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react-native') return Object.fromEntries(['ActivityIndicator', 'Button', 'Text', 'TextInput', 'View'].map(x => [x, x]));
    if (name === 'expo-router') return { Link: 'Link', Stack: { Screen: 'Screen' }, useFocusEffect: focus };
    if (name.endsWith('/components/Page')) return { Page: 'Page', ui: { card: {} } };
    if (name.endsWith('/organizations/rosters')) return rosters;
    if (name.endsWith('/api/client')) return client;
    throw Error(name);
  })[component];
  function nodes(node = tree) { if (Array.isArray(node)) return node.flatMap(n => nodes(n)); if (!node || typeof node !== 'object') return []; return [node, ...nodes(node.props?.children || [])]; }
  const render = () => { slot = 0; tree = Screen(props); while (effects.length) effects.shift()(); };
  async function settle() {
    for (let i = 0; i < 30; i++) {
      await Promise.allSettled([...pending]); await new Promise(setImmediate); render();
      if (!pending.size && i > 2) return;
    }
    throw Error('Mobile screen requests did not settle');
  }
  async function press(title) { const button = nodes().find(n => n.props.title === title); assert.ok(button, `Missing ${title}`); assert.ok(!button.props.disabled, `Disabled ${title}`); button.props.onPress(); await settle(); }
  function fill(label, value) { const input = nodes().find(n => n.props.accessibilityLabel === label); assert.ok(input, label); input.props.onChangeText(value); render(); }
  render();
  return { nodes, settle, press, fill, card(name) { const node = nodes().find(n => n.props.entry?.name === name); assert.ok(node, `Missing card ${name}`); return controller(user, 'TagCard', node.props); } };
}
(async () => {
  const owner = controller('owner'); await owner.settle();
  await owner.press('Roster E2E Academy');
  owner.fill('Talent name', 'Mobile unclaimed ✓'); owner.fill('Tag', 'Player'); owner.fill('Roster', 'First team');
  await owner.press('Add talent');
  const unclaimed = owner.card('Mobile unclaimed ✓');
  assert.ok(unclaimed.nodes().some(n => n.type === 'Text' && JSON.stringify(n.props.children).includes('UNCLAIMED')));
  unclaimed.fill('Link username', fixture.talent_username); await unclaimed.press('Request profile confirmation'); await owner.settle();
  const talent = controller('talent'); await talent.settle();
  const pendingCard = talent.card('Mobile unclaimed ✓'); await pendingCard.press('Confirm affiliation'); await talent.settle();
  assert.equal((await api('outsider')(`organizations/${fixture.organization}/roster/public/`)).count, 1);
  await assert.rejects(() => api('outsider')(`organizations/${fixture.organization}/roster/`), /403/);
  // Losing staff access must not remove personal affiliation controls.
  await talent.press('Roster E2E Academy');
  await api('owner')(`organizations/${fixture.organization}/team/members/${fixture.talent_membership}/remove/`, { method: 'POST', body: {} });
  await talent.press('Refresh rosters');
  const confirmed = talent.card('Mobile unclaimed ✓');
  await confirmed.press('Remove tag'); await confirmed.press('Keep tag');
  assert.equal((await api('outsider')(`organizations/${fixture.organization}/roster/public/`)).count, 1);
  await confirmed.press('Remove tag'); confirmed.fill('Action reason', 'Moved teams'); await confirmed.press('Confirm removal'); await talent.settle();
  assert.equal((await api('outsider')(`organizations/${fixture.organization}/roster/public/`)).count, 0);
  const removed = talent.card('Mobile unclaimed ✓'); await removed.press('View history');
  const historyText = JSON.stringify(removed.nodes().filter(n => n.type === 'Text'));
  for (const action of ['CREATED', 'LINK', 'CONFIRM', 'REMOVE', 'Moved teams']) assert.ok(historyText.includes(action), action);
  await owner.press('Refresh rosters'); owner.fill('Talent name', 'Mobile declined'); owner.fill('Tag', 'Alumni'); owner.fill('Awinlink username (optional)', fixture.talent_username);
  await owner.press('Add talent'); await talent.press('Refresh rosters');
  await talent.card('Mobile declined').press('Decline affiliation'); await talent.settle();
  assert.ok(JSON.stringify(talent.card('Mobile declined').nodes()).includes('DECLINED'));
  assert.equal((await api('outsider')(`organizations/${fixture.organization}/roster/public/`)).count, 0);
  console.log(JSON.stringify({ passed: true, checks: ['unclaimed', 'link', 'confirm', 'JWT permissions', 'revocation', 'cancel removal', 'remove', 'history', 'decline'] }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
