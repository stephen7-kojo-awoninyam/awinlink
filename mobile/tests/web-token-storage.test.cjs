const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

test('web credentials round trip in session storage and are removed on logout', async () => {
  const values = new Map();
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/auth/tokenStorage.web.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, window: { sessionStorage: {
    getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key),
  } } });
  assert.equal(await exports.getItemAsync('access'), null);
  await exports.setItemAsync('access', 'temporary');
  assert.equal(await exports.getItemAsync('access'), 'temporary');
  await exports.deleteItemAsync('access');
  assert.equal(await exports.getItemAsync('access'), null);
});


function authFixture(saved = false) {
  const values = new Map(saved ? [['awinlink.access-token', 'access'], ['awinlink.refresh-token', 'refresh']] : []);
  const storage = {};
  const compile = file => ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(compile('../src/auth/tokenStorage.web.ts'), { exports: storage, window: { sessionStorage: {
    getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key),
  } } });
  const user = { id: 7, username: 'browser-caller' };
  const effects = [], states = []; let cursor = 0, initialized = false;
  const react = {
    createContext: () => ({ Provider: 'provider' }), useCallback: fn => fn, useMemo: fn => fn(),
    useState: initial => { const index = cursor++; if (!(index in states)) states[index] = initial; return [states[index], value => { states[index] = value; }]; },
    useEffect: fn => { if (!initialized) effects.push(fn); },
  };
  const api = {
    ApiError: class extends Error {}, onSessionCleared: () => () => {}, loadCurrentUser: async () => user,
    signInRequest: async () => ({ access: 'access', refresh: 'refresh', user }), revokeCurrentSession: async () => {},
    storeTokens: async (access, refresh) => { await storage.setItemAsync('awinlink.access-token', access); await storage.setItemAsync('awinlink.refresh-token', refresh); },
    clearTokens: async () => { await storage.deleteItemAsync('awinlink.access-token'); await storage.deleteItemAsync('awinlink.refresh-token'); },
  };
  const exports = {};
  vm.runInNewContext(compile('../src/auth/AuthProvider.tsx'), { exports,
    require: name => ({ react, '@/src/auth/tokenStorage': storage, '@/src/api/client': api, '@/src/google': {},
      'react/jsx-runtime': { jsx: (_type, props) => props },
    })[name],
  });
  function render() { cursor = 0; const view = exports.AuthProvider({}); initialized = true; return view.value; }
  render(); effects.forEach(fn => fn());
  return { values, render, user };
}

test('web authentication restores the caller and cached user from browser session storage', async () => {
  const view = authFixture(true);
  await new Promise(setImmediate);
  assert.equal(view.render().user.id, 7);
  assert.equal(view.render().isLoading, false);
  assert.equal(view.render().sessionError, null);
  assert.equal(JSON.parse(view.values.get('awinlink.user')).username, 'browser-caller');
});

test('web sign-in and logout use the same storage as authenticated calling', async () => {
  const view = authFixture();
  await new Promise(setImmediate);
  await view.render().signIn('browser-caller', 'password');
  assert.equal(view.render().user.id, 7);
  assert.equal(view.values.get('awinlink.access-token'), 'access');
  assert.ok(view.values.get('awinlink.user'));
  await view.render().signOut();
  assert.equal(view.render().user, null);
  assert.equal(view.values.size, 0);
});
