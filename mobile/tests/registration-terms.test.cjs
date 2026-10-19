const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(path, imports, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, URL, Error, ...globals, require: name => {
    if (!(name in imports)) throw new Error(`Unexpected import ${name}`);
    return imports[name];
  } });
  return exports;
}

const legal = load('../src/legal.ts', {}, { process: { env: { EXPO_PUBLIC_API_URL: 'https://awinlink.example/api/' } } });

function screen({ fail = false } = {}) {
  const states = [], requests = [], navigation = [], links = [];
  let index = 0;
  const jsx = (type, props) => ({ type, props });
  const react = { useState(initial) {
    const slot = index++;
    if (!(slot in states)) states[slot] = initial;
    return [states[slot], value => { states[slot] = typeof value === 'function' ? value(states[slot]) : value; }];
  } };
  const exports = load('../app/register.tsx', {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': {
      ActivityIndicator: 'Spinner', KeyboardAvoidingView: 'Keyboard', Platform: { OS: 'ios' },
      Pressable: 'Pressable', ScrollView: 'Scroll', Text: 'Text', TextInput: 'Input', View: 'View',
      StyleSheet: { create: value => value }, Linking: { openURL: async url => { links.push(url); } },
    },
    'expo-router': { Redirect: 'Redirect', Stack: { Screen: 'Screen' }, useRouter: () => ({ replace: path => navigation.push(path) }) },
    'react-native-safe-area-context': { SafeAreaView: 'SafeArea' },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user: null, isLoading: false, signUp: async data => {
      requests.push(data); if (fail) throw new Error('The Terms have changed. Reload registration.');
    } }) },
    '@/src/theme': { colors: {} }, '@/src/legal': legal,
  });
  function nodes(node) {
    return node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : [];
  }
  const render = () => { index = 0; return nodes(exports.default()); };
  const checkbox = () => render().find(node => node.props?.accessibilityRole === 'checkbox');
  const submit = () => render().find(node => node.props?.accessibilityRole === 'button' && node.props.children?.props?.children === 'Create account');
  return { render, checkbox, submit, requests, navigation, links };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('mobile Terms version matches the server and links use the configured server root', () => {
  const server = fs.readFileSync(require.resolve('../../accounts/legal.py'), 'utf8');
  assert.ok(server.includes(`TERMS_VERSION = "${legal.TERMS_VERSION}"`));
  assert.equal(legal.policyUrl('terms'), 'https://awinlink.example/terms/');
  assert.equal(legal.policyUrl('privacy'), 'https://awinlink.example/privacy/');
  assert.equal(legal.policyUrl('community-guidelines'), 'https://awinlink.example/community-guidelines/');
});

test('registration starts unchecked and cannot submit without affirmative acceptance', async () => {
  const view = screen();
  assert.equal(view.checkbox().props.accessibilityState.checked, false);
  view.submit().props.onPress(); await flush();
  assert.equal(view.requests.length, 0);
  assert.equal(view.navigation.length, 0);
});

test('reading policies does not accept Terms', async () => {
  const view = screen();
  for (const link of view.render().filter(node => node.props?.accessibilityRole === 'link')) link.props.onPress();
  await flush();
  assert.equal(view.links.length, 3);
  assert.equal(view.checkbox().props.accessibilityState.checked, false);
});

test('all roles send explicit versioned acceptance and preserve onboarding destinations', async () => {
  for (const role of ['ATHLETE', 'ORGANIZATION', 'SCOUT', 'COACH']) {
    const view = screen();
    view.render().find(node => node.props?.key === role || node.props?.children?.props?.children === ({ ATHLETE: 'Talent', ORGANIZATION: 'Organization', SCOUT: 'Scout', COACH: 'Coach' })[role])?.props.onPress();
    view.checkbox().props.onPress();
    view.submit().props.onPress(); await flush();
    assert.equal(view.requests.length, 1);
    assert.equal(view.requests[0].role, role);
    assert.equal(view.requests[0].terms_accepted, true);
    assert.equal(view.requests[0].terms_version, legal.TERMS_VERSION);
    assert.equal(view.navigation[0], ['ATHLETE', 'ORGANIZATION'].includes(role) ? '/onboarding' : '/(tabs)');
  }
});

test('server rejection does not navigate and unchecking prevents resubmission', async () => {
  const view = screen({ fail: true });
  view.checkbox().props.onPress();
  view.submit().props.onPress(); await flush();
  assert.equal(view.navigation.length, 0);
  assert.ok(view.render().some(node => node.props?.children === 'The Terms have changed. Reload registration.'));
  view.checkbox().props.onPress();
  view.submit().props.onPress(); await flush();
  assert.equal(view.requests.length, 1);
});
