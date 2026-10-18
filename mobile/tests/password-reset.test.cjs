const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function screen(initialParams = {}, { fail = false } = {}) {
  const values = [], refs = [], requests = [], navigation = [], effects = [], dependencies = [];
  let params = initialParams, stateIndex = 0, refIndex = 0, effectIndex = 0, cleared = 0;
  const react = {
    useState(initial) {
      const slot = stateIndex++;
      if (!(slot in values)) values[slot] = initial;
      return [values[slot], value => { values[slot] = value; }];
    },
    useRef(initial) { return refs[refIndex++] ||= { current: initial }; },
    useEffect(effect, deps) {
      const slot = effectIndex++;
      if (!dependencies[slot] || deps.some((value, i) => value !== dependencies[slot][i])) {
        effects.push(effect); dependencies[slot] = deps;
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../app/password-reset.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, require: name => ({
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Pressable: 'Pressable', Text: 'Text', TextInput: 'TextInput' },
    'expo-router': {
      Stack: { Screen: 'Screen' }, useLocalSearchParams: () => params,
      useRouter: () => ({ replace: route => navigation.push(route), setParams: changes => { params = { ...params, ...changes }; } }),
    },
    '@/src/api/client': {
      apiRequest: async (path, options) => { requests.push({ path, options }); if (fail) throw new Error('This reset link is invalid or expired.'); return { detail: 'Instructions or password updated.' }; },
      clearTokens: async () => { cleared++; },
    },
    '@/src/components/Page': { Page: 'Page', ui: {} }, '@/src/theme': { colors: {} },
  })[name] });
  function nodes(node) { return node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : []; }
  function render() {
    stateIndex = refIndex = effectIndex = 0;
    const tree = exports.default();
    if (effects.length) { effects.splice(0).forEach(fn => fn()); return render(); }
    return tree;
  }
  const all = () => nodes(render());
  const field = label => all().find(n => n.type === 'TextInput' && n.props.accessibilityLabel === label);
  const button = label => all().find(n => n.type === 'Pressable' && nodes(n).some(x => x.type === 'Text' && x.props.children === label));
  return { field, button, requests, navigation, all, params: () => params, cleared: () => cleared,
    link: value => { params = value; render(); } };
}

test('requests recovery with registered email without sending auth and blocks duplicate taps', async () => {
  const view = screen();
  view.field('Email address').props.onChangeText(' member@example.com ');
  const button = view.button('Send reset instructions');
  button.props.onPress(); button.props.onPress(); await flush();
  assert.equal(view.requests.length, 1);
  assert.equal(view.requests[0].path, 'auth/password-reset/');
  assert.equal(view.requests[0].options.authenticated, false);
  assert.equal(view.requests[0].options.body.email, 'member@example.com');
  assert.equal(view.field('Email address'), undefined);
  assert.ok(view.button('Enter reset code'));
});

test('deep link fills credentials, scrubs route params, and does not auto-submit', () => {
  const view = screen({ uid: 'NA', token: 'signed-token' });
  assert.equal(view.field('Account code'), undefined);
  assert.equal(view.field('Reset token'), undefined);
  assert.equal(view.field('New password').props.secureTextEntry, true);
  assert.equal(view.params().token, undefined);
  assert.equal(view.requests.length, 0);
});

test('password mismatch prevents request and gives readable feedback', async () => {
  const view = screen({ uid: 'NA', token: 'token' });
  view.field('New password').props.onChangeText('Strong!9-Pass');
  view.field('Confirm new password').props.onChangeText('Different!9-Pass');
  view.button('Save new password').props.onPress(); await flush();
  assert.equal(view.requests.length, 0);
  assert.ok(view.all().some(n => n.props?.children === 'Passwords do not match.'));
});

test('successful confirmation clears credentials and session and offers sign-in', async () => {
  const view = screen({ uid: 'NA', token: 'token' });
  view.field('New password').props.onChangeText('Strong!9-Pass');
  view.field('Confirm new password').props.onChangeText('Strong!9-Pass');
  view.button('Save new password').props.onPress(); await flush();
  assert.equal(view.requests[0].path, 'auth/password-reset/confirm/');
  assert.equal(view.requests[0].options.body.token, 'token');
  assert.equal(view.cleared(), 1);
  assert.equal(view.field('New password'), undefined);
  view.button('Back to sign in').props.onPress();
  assert.equal(view.navigation.at(-1), '/login');
});

test('expired link can request another email and clears entered passwords', async () => {
  const view = screen({ uid: 'NA', token: 'expired' }, { fail: true });
  view.field('New password').props.onChangeText('Strong!9-Pass');
  view.field('Confirm new password').props.onChangeText('Strong!9-Pass');
  view.button('Save new password').props.onPress(); await flush();
  assert.ok(view.all().some(n => n.props?.children === 'This reset link is invalid or expired.'));
  view.button('Request a new reset email').props.onPress();
  assert.ok(view.field('Email address'));
  view.button('Enter reset code').props.onPress();
  assert.equal(view.field('New password').props.value, '');
});

test('new warm deep link replaces old credentials and clears password fields', async () => {
  const view = screen({ uid: 'OLD', token: 'old-token' });
  view.field('New password').props.onChangeText('DoNotKeep!9');
  view.link({ uid: 'NEW', token: 'new-token' });
  assert.equal(view.field('New password').props.value, '');
  assert.equal(view.requests.length, 0);
  view.field('New password').props.onChangeText('Strong!9-Pass');
  view.field('Confirm new password').props.onChangeText('Strong!9-Pass');
  view.button('Save new password').props.onPress(); await flush();
  assert.equal(view.requests[0].options.body.uid, 'NEW');
  assert.equal(view.requests[0].options.body.token, 'new-token');
});

test('repeated query parameters are not treated as reset credentials', () => {
  const view = screen({ uid: ['NA', 'NB'], token: ['one', 'two'] });
  assert.ok(view.field('Email address'));
  assert.equal(view.requests.length, 0);
});
