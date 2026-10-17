const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function screen({ fail = false } = {}) {
  const values = [], refs = [], focuses = [], requests = [], routes = [];
  let index = 0, refIndex = 0;
  const connection = { id: 33, sender_id: 2, receiver_id: 1, sender_username: 'target', status: 'PENDING' };
  const react = {
    useState: initial => { const slot = index++; if (!(slot in values)) values[slot] = initial; return [values[slot], value => { values[slot] = typeof value === 'function' ? value(values[slot]) : value; }]; },
    useRef: initial => refs[refIndex++] ||= { current: initial },
    useCallback: fn => fn, useEffect() {},
  };
  const apiRequest = async (url, options) => {
    requests.push({ url, options });
    if (options) { if (fail) throw new Error('Request failed'); return { ...connection, status: options.body.status }; }
    return url === 'connections/received/' ? [connection] : [];
  };
  const jsx = (type, props) => ({ type, props });
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../app/connections.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, require: name => ({
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Pressable: 'Pressable', Text: 'Text', View: 'View', StyleSheet: { create: x => x } },
    'expo-router': { Stack: { Screen: 'Screen' }, useLocalSearchParams: () => ({ id: '4' }), useRouter: () => ({ push: url => routes.push(url) }), useFocusEffect: fn => focuses.push(fn) },
    '@/src/api/client': { apiRequest }, '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 1 } }) },
    '@/src/components/Page': { Page: 'Page', ui: {} }, '@/src/components/EmptyState': {}, '@/src/components/SafetyActions': {}, '@/src/theme': { colors: {} },
  })[name] });
  function nodes(node) { if (!node || typeof node !== 'object') return []; return [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)]; }
  function render() { index = 0; refIndex = 0; return exports.default(); }
  function button(label) { return nodes(render()).find(node => node.type === 'Pressable' && nodes(node).some(child => child.type === 'Text' && child.props.children === label)); }
  render(); focuses[0]();
  return { values, button, requests, routes, focus: () => focuses.at(-1)() };
}

test('accept updates connected list and ignores rapid duplicate taps', async () => {
  const view = screen(); await flush();
  const button = view.button('Accept'); button.props.onPress(); button.props.onPress(); await flush();
  assert.equal(view.requests.filter(r => r.options).length, 1);
  assert.equal(view.requests.find(r => r.options).url, 'connections/33/respond/');
  assert.equal(view.values[0].length, 0); assert.equal(view.values[2][0].status, 'ACCEPTED');
});
test('decline removes incoming request without adding connection', async () => {
  const view = screen(); await flush(); view.button('Decline').props.onPress(); await flush();
  assert.equal(view.values[0].length, 0); assert.equal(view.values[2].length, 0);
});
test('failed response leaves request retryable', async () => {
  const view = screen({ fail: true }); await flush(); view.button('Accept').props.onPress(); await flush();
  assert.equal(view.values[0].length, 1); assert.equal(view.values[2].length, 0);
  assert.equal(view.button('Accept').props.disabled, false);
});
