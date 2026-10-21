const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function screen({ following = false, state = 'none', own = false, fail = false } = {}) {
  const values = [], refs = [], focuses = [], requests = [], routes = [];
  let index = 0, refIndex = 0;
  const profile = { id: 4, user: { id: own ? 1 : 2, username: 'target' } };
  const connection = { id: 7, sender_id: state === 'incoming' ? 2 : 1, receiver_id: state === 'incoming' ? 1 : 2, status: state === 'connected' ? 'ACCEPTED' : 'PENDING' };
  const react = {
    useState: initial => { const slot = index++; if (!(slot in values)) values[slot] = initial; return [values[slot], value => { values[slot] = typeof value === 'function' ? value(values[slot]) : value; }]; },
    useRef: initial => refs[refIndex++] ||= { current: initial },
    useCallback: fn => fn, useEffect() {},
  };
  const apiRequest = async (url, options) => {
    requests.push({ url, options });
    if (options) {
      if (fail) throw new Error('Request failed');
      if (url === 'connections/create/') { state = 'pending'; return { ...connection, status: 'PENDING' }; }
      following = !following; return { followers_count: 3, following_count: 1 };
    }
    if (url === 'talents/4/') return profile;
    if (url === 'follows/following/') return following ? [{ following_id: 2 }] : [];
    if (url === 'connections/') return state === 'connected' ? [connection] : [];
    if (url === 'connections/incoming/') return state === 'incoming' ? [connection] : [];
    if (url === 'connections/outgoing/') return state === 'pending' ? [connection] : [];
    return [];
  };
  const jsx = (type, props) => ({ type, props });
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../app/talent/[id].tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, require: name => ({
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Pressable: 'Pressable', Text: 'Text', View: 'View', StyleSheet: { create: x => x } },
    'expo-router': { Stack: { Screen: 'Screen' }, useLocalSearchParams: () => ({ id: '4' }), useRouter: () => ({ push: url => routes.push(url) }), useFocusEffect: fn => focuses.push(fn) },
    '@/src/api/client': { apiRequest }, '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 1 } }) },
    '@/src/organizations/Badges': { OrganizationBadges: 'OrganizationBadges' },
    '@/src/components/Page': { Page: 'Page', ui: {} }, '@/src/components/EmptyState': {}, '@/src/components/SafetyActions': {}, '@/src/theme': { colors: {} },
  })[name] });
  function nodes(node) { if (!node || typeof node !== 'object') return []; return [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)]; }
  function render() { index = 0; refIndex = 0; return exports.default(); }
  function button(label) { return nodes(render()).find(node => node.type === 'Pressable' && nodes(node).some(child => child.type === 'Text' && child.props.children === label)); }
  render(); focuses[0]();
  return { button, requests, routes, focus: () => focuses.at(-1)() };
}

test('following users can connect and sending preserves independent follow state', async () => {
  const view = screen({ following: true }); await flush();
  assert.equal(view.button('Connect').props.disabled, false);
  const connect = view.button('Connect');
  connect.props.onPress(); connect.props.onPress(); await flush();
  assert.ok(view.button('Following'));
  assert.equal(view.button('Request sent').props.disabled, true);
  const sent = view.requests.find(item => item.url === 'connections/create/');
  assert.equal(sent.options.body.receiver, 2);
  assert.equal(view.requests.filter(item => item.url === 'connections/create/').length, 1);
});

test('follow toggles preserve connected, incoming and outgoing request states', async () => {
  for (const [state, label] of [['connected', 'Connected'], ['pending', 'Request sent'], ['incoming', 'Request received']]) {
    const view = screen({ state }); await flush();
    view.button('Follow').props.onPress(); await flush();
    assert.ok(view.button('Following'));
    assert.ok(view.button(label));
    if (state === 'incoming') { view.button(label).props.onPress(); assert.equal(view.routes[0], '/connections'); }
    else assert.equal(view.button(label).props.disabled, true);
  }
});

test('failed connection remains retryable and own profile has no connect action', async () => {
  const view = screen({ fail: true }); await flush();
  view.button('Connect').props.onPress(); await flush();
  assert.equal(view.button('Connect').props.disabled, false);
  assert.equal(view.button('Request sent'), undefined);
  const own = screen({ own: true }); await flush();
  assert.equal(own.button('Connect'), undefined);
});
