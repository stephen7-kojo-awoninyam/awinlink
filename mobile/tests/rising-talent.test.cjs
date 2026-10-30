const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };

function harness(request, initialUser = { id: 1, role: 'SCOUT' }) {
  let user = initialUser, slot = 0, tree;
  const values = [], effects = [];
  const react = {
    useState(initial) { const i = slot++; if (!(i in values)) values[i] = initial; return [values[i], next => { values[i] = typeof next === 'function' ? next(values[i]) : next; }]; },
    useRef(initial) { const i = slot++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
    useCallback(fn, deps) { const i = slot++; const old = values[i]; if (!old || deps.some((v, j) => old.deps[j] !== v)) values[i] = { fn, deps }; return values[i].fn; },
  };
  const focus = fn => { const i = slot++; if (values[i]?.fn !== fn) { values[i]?.cleanup?.(); const value = values[i] = { fn }; effects.push(() => { value.cleanup = fn(); }); } };
  const jsx = (type, props) => ({ type, props: props || {} });
  const module = { exports: {} };
  const source = readFileSync(resolve(__dirname, '../app/rising-talent.tsx'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, {
    module, exports: module.exports,
    require: name => {
      if (name === '@/src/paged-state') return require('./pagination-helpers.cjs').pagedState(react);
      if (name === '@/src/components/LoadMore') return { LoadMore: 'LoadMore' };
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
      if (name === 'react-native') return Object.fromEntries(['ActivityIndicator', 'Button', 'Pressable', 'Text', 'TextInput', 'View'].map(x => [x, x]));
      if (name === 'expo-router') return { Link: 'Link', Stack: { Screen: 'Screen' }, useFocusEffect: focus };
      if (name.endsWith('/auth/AuthProvider')) return { useAuth: () => ({ user }) };
      if (name.endsWith('/api/client')) return { apiRequest: request };
      if (name.endsWith('/components/Page')) return { Page: 'Page', ui: { card: {} } };
      throw Error(name);
    },
  });
  const collect = node => Array.isArray(node) ? node.flatMap(collect) : node && typeof node === 'object' ? [node, ...collect(node.props?.children)] : [];
  return { render() { slot = 0; tree = module.exports.default(); while (effects.length) effects.shift()(); }, nodes: () => collect(tree), setUser(next) { user = next; } };
}

const blank = { discovery_enabled: false, alerts_enabled: false, category: '', skills: [], organization: null, selected_skills: [] };
const options = { categories: [{ id: 'ARTS', name: 'Arts' }], skills: [{ id: 2, name: 'Design' }], organizations: [{ id: 4, name: 'Arts academy' }] };

test('mobile recipient selects explicit interests, opts into alerts and submits only own settings', async () => {
  const calls = [];
  let saved = blank;
  const h = harness(async (url, args) => {
    calls.push({ url, args });
    if (args?.method === 'PATCH') { saved = { ...args.body, selected_skills: [{ id: 2, name: 'Design' }] }; return saved; }
    return url.includes('preferences') ? saved : url.includes('options') ? options : { results: [], assessment: null };
  });
  h.render(); await flush(); h.render();
  assert.equal(h.nodes().find(n => n.props.accessibilityRole === 'checkbox').props.accessibilityState.checked, false);
  h.nodes().find(n => n.props.title === 'Arts').props.onPress(); h.render();
  h.nodes().find(n => n.props.title === 'Add Design').props.onPress(); h.render();
  h.nodes().find(n => n.props.accessibilityRole === 'checkbox').props.onPress(); h.render();
  const save = h.nodes().find(n => n.props.title === 'Save Rising Talent preferences');
  save.props.onPress(); save.props.onPress(); await flush(); h.render();
  const writes = calls.filter(row => row.args?.method === 'PATCH');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].args.body.alerts_enabled, true);
  assert.equal(writes[0].args.body.category, 'ARTS');
  assert.deepEqual(Array.from(writes[0].args.body.skills), [2]);
  assert.ok(!('user_id' in writes[0].args.body));
  assert.ok(JSON.stringify(h.nodes()).includes('preferences saved'));
});

test('mobile talents explicitly enable and withdraw discovery and see their own evidence', async () => {
  let saved = { ...blank };
  const h = harness(async (url, args) => {
    if (args?.method === 'PATCH') { saved = { ...args.body, selected_skills: [] }; return saved; }
    if (url.includes('preferences')) return saved;
    if (url.includes('options')) return options;
    return { results: [], assessment: saved.discovery_enabled ? { score: 65, qualified: true, explanations: ['3 dated achievements; no skill growth points.'] } : null };
  }, { id: 1, role: 'ATHLETE' });
  h.render(); await flush(); h.render();
  assert.equal(h.nodes().filter(n => n.props.accessibilityRole === 'checkbox').length, 1);
  h.nodes().find(n => n.props.accessibilityRole === 'checkbox').props.onPress(); h.render();
  h.nodes().find(n => n.props.title === 'Save Rising Talent preferences').props.onPress(); await flush(); h.render();
  assert.ok(JSON.stringify(h.nodes()).includes('3 dated achievements'));
  h.nodes().find(n => n.props.accessibilityRole === 'checkbox').props.onPress(); h.render();
  h.nodes().find(n => n.props.title === 'Save Rising Talent preferences').props.onPress(); await flush(); h.render();
  assert.equal(saved.discovery_enabled, false);
  assert.ok(!JSON.stringify(h.nodes()).includes('3 dated achievements'));
});

test('mobile displays match explanations and preserves choices after server validation failure', async () => {
  const h = harness(async (url, args) => {
    if (args?.method === 'PATCH') throw Error('Choose relevant skills.');
    return url.includes('preferences') ? blank : url.includes('options') ? options : {
      assessment: null, results: [{ talent_id: 8, name: '<script>person</script>', category_name: 'Arts',
        match_explanation: 'Matches your Design skill.', assessment: { score: 65, qualified: true, explanations: ['3 dated achievements.'] } }],
    };
  });
  h.render(); await flush(); h.render();
  assert.ok(JSON.stringify(h.nodes()).includes('Matches your Design skill.'));
  h.nodes().find(n => n.props.title === 'Arts').props.onPress(); h.render();
  h.nodes().find(n => n.props.title === 'Save Rising Talent preferences').props.onPress(); await flush(); h.render();
  assert.ok(h.nodes().some(n => n.props.accessibilityRole === 'alert'));
  assert.ok(h.nodes().some(n => n.props.title === 'Selected: Arts'));
});

test('mobile discards stale results when the authenticated account changes', async () => {
  const pending = [];
  const h = harness(url => new Promise(resolve => pending.push({ url, resolve })));
  h.render();
  h.setUser({ id: 2, role: 'COACH' }); h.render();
  for (const row of pending.slice(3)) row.resolve(row.url.includes('preferences') ? blank : row.url.includes('options') ? options : { results: [], assessment: null });
  await flush(); h.render();
  for (const row of pending.slice(0, 3)) row.resolve(row.url.includes('preferences') ? blank : row.url.includes('options') ? options : { results: [{ talent_id: 99, name: 'Stale private match', category_name: 'Arts', assessment: { score: 65, explanations: [] } }], assessment: null });
  await flush(); h.render();
  assert.ok(!JSON.stringify(h.nodes()).includes('Stale private match'));
});

test('mobile withdrawal submits only consent flags so stale interests cannot prevent opting out', async () => {
  const writes = [];
  const h = harness(async (url, args) => {
    if (args?.method === 'PATCH') { writes.push(args.body); return blank; }
    return url.includes('preferences') ? { ...blank, alerts_enabled: true, organization: 99999 } : url.includes('options') ? options : { results: [], assessment: null };
  });
  h.render(); await flush(); h.render();
  h.nodes().find(n => n.props.title === 'Turn off Rising Talent').props.onPress(); await flush(); h.render();
  assert.deepEqual(Object.keys(writes[0]).sort(), ['alerts_enabled', 'discovery_enabled']);
  assert.equal(writes[0].alerts_enabled, false);
  assert.equal(writes[0].discovery_enabled, false);
});

test('mobile displays an evidence limit as paused matching rather than a low talent score', async () => {
  const h = harness(async url => url.includes('preferences') ? blank : url.includes('options') ? options : {
    results: [], assessment: { score: 0, qualified: false, evidence_complete: false,
      explanations: ['Automatic matching is paused because this profile exceeds the evidence review limit. No score was assigned.'] },
  }, { id: 1, role: 'ATHLETE' });
  h.render(); await flush(); h.render();
  assert.ok(JSON.stringify(h.nodes()).includes('Automatic matching paused. No score was assigned.'));
  assert.ok(!JSON.stringify(h.nodes()).includes('0/100'));
});
