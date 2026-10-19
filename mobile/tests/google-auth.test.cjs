const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, imports, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, URL, ...globals, require: name => {
    if (!(name in imports)) throw new Error(`Unexpected import: ${name}`);
    return imports[name];
  } });
  return exports;
}

function googleClient(result = { type: 'success', url: 'awinlink://google-complete?handoff=browser-proof' }) {
  const requests = [], browsers = [];
  const api = load('../src/google.ts', {
    'expo-web-browser': { openAuthSessionAsync: async (...args) => { browsers.push(args); return result; } },
    '@/src/api/client': { apiRequest: async (path, options) => {
      requests.push({ path, options });
      return path.endsWith('start/') ? { authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=bound', exchange_secret: 'private-exchange' } : { signup_required: true };
    } },
  });
  return { api, requests, browsers };
}

test('native browser flow uses private exchange without credentials in the return URL', async () => {
  const view = googleClient();
  const exchange = await view.api.beginGoogle(false, '');
  assert.equal(exchange.exchange_secret, 'private-exchange');
  assert.equal(exchange.handoff, 'browser-proof');
  assert.equal(view.browsers[0][1], 'awinlink://google-complete');
  assert.equal(view.requests[0].options.authenticated, false);
  assert.equal(view.requests[0].options.body.link, false);
  assert.equal('password' in view.requests[0].options.body, false);
  await view.api.exchangeGoogle({ exchange_secret: 'private-exchange', handoff: 'browser-proof' }, { role: 'COACH', terms_accepted: true });
  assert.equal(view.requests[1].path, 'auth/google/complete/');
  assert.equal(view.requests[1].options.body.exchange_secret, 'private-exchange');
  assert.equal(view.requests[1].options.body.signup.terms_accepted, true);
});

test('cancelled browser and unexpected redirect never redeem a secret', async () => {
  for (const result of [{ type: 'cancel' }, { type: 'dismiss' }, { type: 'success', url: 'awinlink://attacker?token=bad' }]) {
    const view = googleClient(result);
    await assert.rejects(view.api.beginGoogle(false, ''), /cancelled/);
    assert.equal(view.requests.length, 1);
  }
});

test('explicit linking authenticates start and completion and requires password proof', async () => {
  const view = googleClient();
  await view.api.beginGoogle(true, 'current-password');
  await view.api.exchangeGoogle({ exchange_secret: 'private-exchange', handoff: 'browser-proof' }, undefined, true);
  assert.equal(view.requests[0].options.authenticated, true);
  assert.equal(view.requests[0].options.body.password, 'current-password');
  assert.equal(view.requests[1].options.authenticated, true);
  assert.equal('password' in view.requests[1].options.body, false);
});

function screen({ needsSignup = true } = {}) {
  const states = [], requests = [], navigation = [];
  let index = 0;
  const jsx = (type, props) => ({ type, props });
  const react = { useState(initial) {
    const slot = index++;
    if (!(slot in states)) states[slot] = initial;
    return [states[slot], value => { states[slot] = typeof value === 'function' ? value(states[slot]) : value; }];
  } };
  const exports = load('../app/google-auth.tsx', {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': { Pressable: 'Button', Text: 'Text', TextInput: 'Input', View: 'View', ScrollView: 'Scroll', Platform: { OS: 'ios' }, Linking: { openURL: async () => {} } },
    'expo-router': { Redirect: 'Redirect', Stack: { Screen: 'Screen' }, useLocalSearchParams: () => ({}), useRouter: () => ({ replace: path => navigation.push(path) }) },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user: null, isLoading: false, signInGoogle: async (secret, signup) => {
      requests.push({ secret, signup });
      if (signup || !needsSignup) return { access: 'access', refresh: 'refresh', user: { role: 'ATHLETE' } };
      return { signup_required: true, email: 'verified@example.com' };
    } }) },
    '@/src/google': { beginGoogle: async () => ({ exchange_secret: 'secret-in-memory', handoff: 'browser-proof' }) },
    '@/src/legal': { TERMS_VERSION: 'current', policyUrl: path => `https://awinlink.example/${path}/` },
    '@/src/components/Page': { ui: {} },
  });
  const nodes = node => node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : [];
  const render = () => { index = 0; return nodes(exports.default()); };
  const button = label => render().find(node => node.type === 'Button' && node.props.children?.props?.children === label);
  return { render, button, requests, navigation };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('new Google users cannot skip role or Terms and successful signup retains onboarding', async () => {
  const view = screen();
  view.button('Continue with Google').props.onPress(); await flush();
  assert.equal(view.navigation.length, 0);
  assert.equal(view.render().find(node => node.props?.accessibilityRole === 'checkbox').props.accessibilityState.checked, false);
  view.button('Create account').props.onPress(); await flush();
  assert.equal(view.requests.length, 1);
  view.render().find(node => node.props?.accessibilityRole === 'radio').props.onPress();
  view.button('Create account').props.onPress(); await flush();
  assert.equal(view.requests.length, 1);
  view.render().find(node => node.props?.accessibilityRole === 'checkbox').props.onPress();
  view.button('Create account').props.onPress(); await flush();
  assert.equal(view.requests[1].signup.role, 'ATHLETE');
  assert.equal(view.requests[1].signup.terms_accepted, true);
  assert.equal(view.requests[1].signup.terms_version, 'current');
  assert.equal(view.navigation[0], '/onboarding');
});

test('established Google identity signs in without forcing a new Terms acceptance', async () => {
  const view = screen({ needsSignup: false });
  view.button('Continue with Google').props.onPress(); await flush();
  assert.equal(view.navigation[0], '/(tabs)');
  assert.equal(view.requests[0].signup, undefined);
});
