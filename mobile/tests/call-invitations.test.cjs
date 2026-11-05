const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

function fixture(request, remotes = {}, platform = 'android') {
  let dimensions = { width: 360, height: 640 };
  const slots = []; let cursor = 0;
  const requests = [];
  const react = {
    useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = initial && typeof initial === 'object' ? remotes : initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
    useRef(value) { const index = cursor++; return slots[index] ||= { current: value }; },
    useCallback: fn => fn, useEffect() {},
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/calls/CallScreen.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, Error, __DEV__: false, WebSocket: {},
    require: name => ({
      react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
      'react-native': { useWindowDimensions: () => dimensions, Platform: { OS: platform }, StyleSheet: { create: x => x }, KeyboardAvoidingView: 'keyboard', TextInput: 'input', Text: 'text', Modal: 'modal', View: 'view', ScrollView: 'scroll' },
      'expo-router': { Stack: { Screen: 'screen' }, useLocalSearchParams: () => ({ id: '42' }) },
      'react-native-safe-area-context': {}, '@/src/calls/rtc': { RTCView: 'video', streamURL: value => value.id }, '@/src/api/socketAuthentication': {},
      '@/src/api/client': { apiRequest: async (url, options) => { requests.push({ url, ...options }); return request(); } },
      '@/src/auth/AuthProvider': { useAuth: () => ({ user: { id: 1 } }) }, '@/src/calls/iceServers': {},
      '@/src/calls/callDiagnostics': {}, '@/src/theme': { colors: {} }, '@/src/calls/nativeCallUI': {}, '@/src/calls/callLifecycle': {},
    })[name],
  });
  function render() { cursor = 0; return exports.default(); }
  function nodes(node) { return !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)]; }
  function find(predicate) { return nodes(render()).find(predicate)?.props; }
  return { requests, resize: (width, height) => { dimensions = { width, height }; }, tiles: () => nodes(render()).filter(n => n.type === 'view' && typeof n.props?.style?.height === 'number' && typeof n.props?.style?.width === 'string'), videos: () => nodes(render()).filter(n => n.type === 'video'), control: label => find(n => n.props?.label === label), input: () => find(n => n.type === 'input'), modal: () => find(n => n.type === 'modal'), text: value => find(n => n.props?.children === value) };
}

test('Add person submits a trimmed username and preserves the ongoing call', async () => {
  const screen = fixture(async () => ({}));
  screen.control('Add person').onPress();
  assert.equal(screen.modal().visible, true);
  assert.equal(screen.control('Send invitation').disabled, true);
  screen.input().onChangeText('  guest  ');
  await screen.control('Send invitation').onPress();
  await new Promise(setImmediate);
  assert.equal(screen.requests.length, 1);
  assert.equal(screen.requests[0].url, 'messaging/calls/42/invite/');
  assert.equal(screen.requests[0].body.username, 'guest');
  assert.ok(screen.text('Invitation sent.'));
  assert.equal(screen.input().value, '');
  assert.ok(screen.control('Hang up'));
});

test('invitation failure remains visible and allows retry', async () => {
  const screen = fixture(async () => { throw new Error('Only the call initiator can invite guests.'); });
  screen.control('Add person').onPress(); screen.input().onChangeText('guest');
  screen.control('Send invitation').onPress(); await new Promise(setImmediate);
  assert.ok(screen.text('Only the call initiator can invite guests.'));
  assert.equal(screen.control('Send invitation').disabled, false);
  assert.equal(screen.input().value, 'guest');
});

test('iOS Add person keeps submission available with the software keyboard', async () => {
  const screen = fixture(async () => ({}), {}, 'ios');
  screen.control('Add person').onPress();
  screen.input().onChangeText('  ios_guest  ');
  await screen.input().onSubmitEditing();
  await new Promise(setImmediate);
  assert.equal(screen.requests[0].body.username, 'ios_guest');
  assert.ok(screen.text('Invitation sent.'));
  screen.modal().onRequestClose();
  assert.equal(screen.modal().visible, false);
  assert.ok(screen.control('Hang up'));
});


test('six remote videos remain scrollable and adapt between portrait and landscape', () => {
  const remotes = Object.fromEntries([2, 3, 4, 5, 6, 7].map(id => [id, { id: String(id) }]));
  const screen = fixture(async () => ({}), remotes);
  assert.equal(screen.videos().length, 6);
  assert.equal(screen.tiles().length, 6);
  assert.ok(screen.tiles().every(tile => tile.props.style.width === '100%' && tile.props.style.height >= 140));
  screen.resize(900, 400);
  assert.equal(screen.videos().length, 6);
  assert.ok(screen.tiles().every(tile => tile.props.style.width === '50%' && tile.props.style.height >= 140));
  assert.ok(screen.control('Hang up'));
  assert.ok(screen.control('Add person'));
});
