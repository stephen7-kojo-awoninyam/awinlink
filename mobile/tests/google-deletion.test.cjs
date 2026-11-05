const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function screen({ google = async () => ({ exchange_secret: 'private-proof', handoff: 'browser-proof' }), failDelete = false } = {}) {
  const slots = [], cleanups = [], requests = [], alerts = [];
  let index = 0, user = { id: 7 }, signedOut = 0, browserCalls = 0;
  const jsx = (type, props) => ({ type, props });
  const react = {
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = initial; return [slots[i], v => { slots[i] = v; }]; },
    useRef(initial) { const i = index++; if (!(i in slots)) slots[i] = { current: initial }; return slots[i]; },
    useCallback: f => f,
    useEffect(f) { const i = index++; if (!(i in slots)) { slots[i] = true; cleanups.push(f()); } },
  };
  const imports = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Alert: { alert: (...args) => alerts.push(args) }, Linking: {}, Pressable: 'Button', Text: 'Text', TextInput: 'Input', View: 'View' },
    'expo-router': { Stack: { Screen: 'Stack' }, useFocusEffect() {}, router: { push() {} } },
    '@/src/api/client': { apiRequest: async (path, options) => { requests.push({ path, options }); if (failDelete) throw new Error('Transfer organization ownership'); } },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user, signOut: async () => { signedOut++; } }) },
    '@/src/legal': { policyUrl: p => p }, '@/src/components/Page': { Page: 'Page', ui: {} },
    '@/src/calls/nativeCallUI': { openNativeCallSettings() {} },
    '@/src/google': { beginGoogleDeletion: async () => { browserCalls++; return google(); } },
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../app/account-settings.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, process: { env: {} }, Error, require: n => {
    if (!(n in imports)) throw new Error(`Unexpected import ${n}`);
    return imports[n];
  } });
  const nodes = n => n && typeof n === 'object' ? [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)] : [];
  const render = () => { index = 0; return nodes(exports.default()); };
  const button = label => render().find(n => n.type === 'Button' && n.props.children?.props?.children === label);
  return { render, button, requests, alerts, get signedOut() { return signedOut; }, get browserCalls() { return browserCalls; },
    confirm() { alerts.at(-1)[2].find(b => b.style === 'destructive').onPress(); },
    switchUser(id = 8) { user = { id }; render(); }, unmount() { cleanups.forEach(f => f?.()); } };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('Google-only deletion needs explicit confirmation, sends proof without password, and signs out after success', async () => {
  const v = screen();
  v.button('Delete account with Google').props.onPress();
  assert.equal(v.browserCalls, 0);
  assert.equal(v.requests.length, 0);
  v.confirm(); await flush();
  assert.equal(v.browserCalls, 1);
  assert.equal(v.requests.length, 1);
  assert.equal(v.requests[0].path, 'auth/account/');
  assert.equal(v.requests[0].options.method, 'DELETE');
  assert.equal(v.requests[0].options.body.confirm, true);
  assert.equal(v.requests[0].options.body.google_reauth.exchange_secret, 'private-proof');
  assert.equal('password' in v.requests[0].options.body, false);
  assert.equal(v.signedOut, 1);
});

test('Google cancellation or deletion denial retains the account session and displays the error', async () => {
  for (const options of [{ google: async () => { throw new Error('Google sign-in cancelled'); } }, { failDelete: true }]) {
    const v = screen(options);
    v.button('Delete account with Google').props.onPress(); v.confirm(); await flush();
    assert.equal(v.signedOut, 0);
    assert.ok(v.render().find(n => n.props?.accessibilityRole === 'alert'));
    assert.equal(v.requests.length, options.failDelete ? 1 : 0);
  }
});

test('password deletion keeps its current-password request and confirmation', async () => {
  const v = screen();
  v.render().find(n => n.type === 'Input').props.onChangeText('current-password');
  v.button('Delete account').props.onPress();
  assert.equal(v.requests.length, 0);
  v.confirm(); await flush();
  assert.equal(v.requests[0].options.body.password, 'current-password');
  assert.equal('google_reauth' in v.requests[0].options.body, false);
  assert.equal(v.browserCalls, 0);
  assert.equal(v.signedOut, 1);
});

test('late Google browser results cannot delete after account switching or screen unmount', async () => {
  for (const action of ['switchUser', 'unmount']) {
    let resolve;
    const v = screen({ google: () => new Promise(r => { resolve = r; }) });
    v.button('Delete account with Google').props.onPress(); v.confirm();
    v[action]();
    resolve({ exchange_secret: 'private-proof', handoff: 'browser-proof' }); await flush();
    assert.equal(v.requests.length, 0);
    assert.equal(v.signedOut, 0);
  }
});

test('rapid repeated confirmations share a single deletion operation', async () => {
  let resolve;
  const v = screen({ google: () => new Promise(r => { resolve = r; }) });
  v.button('Delete account with Google').props.onPress();
  v.confirm(); v.confirm();
  assert.equal(v.browserCalls, 1);
  resolve({ exchange_secret: 'private-proof', handoff: 'browser-proof' }); await flush();
  assert.equal(v.requests.length, 1);
});

test('old confirmation dialogs and account round trips cannot authorize deletion', async () => {
  const oldDialog = screen();
  oldDialog.button('Delete account with Google').props.onPress();
  oldDialog.switchUser(); oldDialog.switchUser(7);
  oldDialog.confirm(); await flush();
  assert.equal(oldDialog.browserCalls, 0);
  let resolve;
  const v = screen({ google: () => new Promise(r => { resolve = r; }) });
  v.button('Delete account with Google').props.onPress(); v.confirm();
  v.switchUser(); v.switchUser(7);
  resolve({ exchange_secret: 'private-proof', handoff: 'browser-proof' }); await flush();
  assert.equal(v.requests.length, 0);
  assert.equal(v.signedOut, 0);
});
