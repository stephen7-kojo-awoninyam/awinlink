const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function screen(params = { type: 'safety', id: '0' }, request = async () => ({})) {
  const states = [], effects = [], requests = [];
  let index = 0, user = { id: 1 };
  const jsx = (type, props) => ({ type, props });
  const react = {
    useState(value) { const i = index++; if (!(i in states)) states[i] = value; return [states[i], v => { states[i] = v; }]; },
    useRef(value) { const i = index++; if (!(i in states)) states[i] = { current: value }; return states[i]; },
    useEffect(f, deps) { const i = index++; if (!(i in states) || deps.some((d, j) => d !== states[i][j])) { states[i] = deps; effects.push(f); } },
  };
  const imports = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Pressable: 'Button', Text: 'Text', TextInput: 'Input' },
    'expo-router': { Stack: { Screen: 'Stack' }, useLocalSearchParams: () => params, router: { back() {} } },
    '@/src/components/Page': { Page: 'Page', ui: {} },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user }) },
    '@/src/api/client': { apiRequest: async (path, options) => { requests.push({ path, options }); return request(); } },
  };
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../app/report.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, Number, require: n => { if (!(n in imports)) throw new Error(`Unexpected ${n}`); return imports[n]; } });
  const nodes = n => n && typeof n === 'object' ? [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)] : [];
  const renderOnce = () => { index = 0; return nodes(exports.default()); };
  const render = () => { renderOnce(); while (effects.length) effects.shift()(); return renderOnce(); };
  const submit = () => render().find(n => n.type === 'Button' && n.props.children?.props?.children === 'Submit report');
  return { render, requests, submit, setDetails(s) { render().find(n => n.type === 'Input').props.onChangeText(s); },
    selectReason(i) { render().filter(n => n.props?.accessibilityRole === 'radio')[i].props.onPress(); },
    switchTarget(next) { params = next; render(); }, switchUser(id) { user = { id }; render(); } };
}
const flush = () => new Promise(r => setImmediate(r));

test('general child-safety reporting needs a description and submits without a target record', async () => {
  const v = screen();
  v.submit().props.onPress(); await flush();
  assert.equal(v.requests.length, 0);
  v.setDetails('Call or classroom concern with a time and username');
  v.submit().props.onPress(); await flush();
  assert.equal(v.requests[0].path, 'safety/reports/');
  assert.equal(v.requests[0].options.body.target_type, 'safety');
  assert.equal(v.requests[0].options.body.target_id, 0);
  assert.equal(v.requests[0].options.body.reason, 'child_safety');
  assert.ok(v.render().find(n => n.props?.children === 'Report submitted for review.'));
});

test('existing profile/post/message reporting retains its targets and spam category', async () => {
  for (const type of ['user', 'post', 'message']) {
    const v = screen({ type, id: '7' });
    v.submit().props.onPress(); await flush();
    assert.equal(v.requests[0].options.body.target_type, type);
    assert.equal(v.requests[0].options.body.target_id, 7);
    assert.equal(v.requests[0].options.body.reason, 'spam');
  }
});

test('child-safety category can be selected for an existing item and rejection remains retryable', async () => {
  let fail = true;
  const v = screen({ type: 'post', id: '8' }, async () => { if (fail) throw new Error('Temporarily unavailable'); });
  v.selectReason(4); v.setDetails('A child safety concern about this post');
  v.submit().props.onPress(); await flush();
  assert.equal(v.requests[0].options.body.reason, 'child_safety');
  assert.ok(v.submit());
  fail = false; v.submit().props.onPress(); await flush();
  assert.equal(v.requests.length, 2);
});

test('duplicate taps cannot create concurrent reports and stale responses cannot mark another target sent', async () => {
  let resolve;
  const v = screen({ type: 'post', id: '7' }, () => new Promise(r => { resolve = r; }));
  const first = v.submit(); first.props.onPress(); first.props.onPress();
  assert.equal(v.requests.length, 1);
  v.switchTarget({ type: 'safety', id: '0' });
  resolve({}); await flush();
  assert.ok(v.submit());
  assert.equal(v.submit().props.disabled, false);
});

test('report drafts and late success cannot cross accounts or account round trips', async () => {
  let resolve;
  const v = screen({ type: 'safety', id: '0' }, () => new Promise(r => { resolve = r; }));
  v.setDetails('A sensitive child safety concern');
  v.submit().props.onPress();
  v.switchUser(2); v.switchUser(1);
  assert.equal(v.render().find(n => n.type === 'Input').props.value, '');
  resolve({}); await flush();
  assert.ok(v.submit());
  assert.equal(v.requests.length, 1);
});
