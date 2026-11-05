const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, imports) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, URL, require: name => {
    if (!(name in imports)) throw new Error(`Unexpected import: ${name}`);
    return imports[name];
  } });
  return exports;
}

function auth(result) {
  const writes = [], tokens = [], states = [];
  const jsx = (type, props) => ({ type, props });
  const component = load('../src/auth/AuthProvider.tsx', {
    '@/src/auth/tokenStorage': { setItemAsync: async (...args) => writes.push(args), deleteItemAsync: async () => {} },
    react: {
      createContext: () => ({ Provider: 'Provider' }),
      useState: initial => [initial, value => states.push(value)],
      useCallback: fn => fn, useMemo: fn => fn(), useEffect: () => {}, useContext: () => {},
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    '@/src/api/client': {
      signUpRequest: async () => result, storeTokens: async (...args) => tokens.push(args),
    },
    '@/src/google': { exchangeGoogle: async () => result },
  });
  return { value: component.AuthProvider({ children: null }).props.value, writes, tokens, states };
}

test('pending password and Google registrations never persist credentials or enter a signed-in state', async () => {
  const pending = { guardian_approval_required: true, detail: 'Verified guardian approval required.' };
  for (const method of ['signUp', 'signInGoogle']) {
    const view = auth(pending);
    const result = await view.value[method]({ date_of_birth: '2020-01-01' });
    assert.equal(result.guardian_approval_required, true);
    assert.equal(view.tokens.length, 0);
    assert.equal(view.writes.length, 0);
    assert.equal(view.states.length, 0);
  }
});

test('adult and teen registrations retain token storage and signed-in state', async () => {
  for (const group of ['ADULT', 'TEEN']) {
    const result = { access: 'access', refresh: 'refresh', user: {
      id: 1, username: 'member', role: 'COACH', account_capabilities: { age_group: group },
    } };
    const view = auth(result);
    assert.equal(await view.value.signUp({ date_of_birth: '1990-01-01' }), result);
    assert.deepEqual(Array.from(view.tokens[0]), ['access', 'refresh']);
    assert.equal(JSON.parse(view.writes[0][1]).account_capabilities.age_group, group);
    assert.equal(view.states[0], result.user);
  }
});
