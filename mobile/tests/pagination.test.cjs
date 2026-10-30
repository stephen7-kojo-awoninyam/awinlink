const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { pagination, pagedState } = require('./pagination-helpers.cjs');
const flush = () => new Promise(setImmediate);
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

test('continuations stay on the API origin/path and preserve encoded filters', () => {
  const base = 'https://app.example/api/';
  assert.equal(pagination.continuationPath('<https://app.example/api/talents/?cursor=signed&search=a%26b>; rel="next"', base), 'talents/?cursor=signed&search=a%26b');
  assert.equal(pagination.continuationPath(null, base), null);
  assert.equal(pagination.continuationPath('<https://app.example/api/talents/>; rel="previous"', base), null);
  for (const url of ['https://evil.example/api/talents/', 'https://app.example/account/', 'https://u:p@app.example/api/talents/', 'https://app.example/api/talents/#secret']) {
    assert.throws(() => pagination.continuationPath(`<${url}>; rel="next"`, base), /Invalid pagination URL/);
  }
});

test('pages retain the array contract, deduplicate records and stop at the last page', () => {
  const first = pagination.withNextPage([{ id: 3 }, { id: 2 }], 'talents/?cursor=next');
  assert.equal(JSON.stringify(first), '[{"id":3},{"id":2}]');
  assert.equal(pagination.nextPage(first), 'talents/?cursor=next');
  const merged = pagination.mergePage(first, pagination.withNextPage([{ id: 2 }, { id: 1 }, { id: 1 }], null));
  assert.deepEqual(Array.from(merged, row => row.id), [3, 2, 1]);
  assert.equal(pagination.nextPage(merged), null);
});

function fixture() {
  const values = [], refs = [], effects = [];
  let index = 0, refIndex = 0, user = { id: 1, role: 'ATHLETE' };
  let items = pagination.withNextPage([{ id: 3 }], 'talents/?cursor=next');
  const requests = [], pending = deferred();
  const react = {
    useState(initial) { const slot = index++; if (!(slot in values)) values[slot] = typeof initial === 'function' ? initial() : initial;
      return [values[slot], next => { values[slot] = typeof next === 'function' ? next(values[slot]) : next; }]; },
    useRef(initial) { return refs[refIndex++] ||= { current: initial }; },
    useCallback: fn => fn, useEffect: fn => effects.push(fn),
  };
  const exports = {}, jsx = (type, props) => ({ type, props });
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/components/LoadMore.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, Error, require: name => ({ react,
    'react/jsx-runtime': { jsx, jsxs: jsx }, 'react-native': { Pressable: 'Pressable', Text: 'Text', View: 'View' },
    '@/src/api/client': { apiRequest: path => { requests.push(path); return pending.promise; } },
    '@/src/auth/AuthProvider': { useAuth: () => ({ user }) }, '@/src/pagination': pagination, '@/src/theme': { colors: {} },
  })[name] });
  let cleanup;
  function render() {
    index = refIndex = 0;
    const tree = exports.LoadMore({ items, onChange: next => { items = typeof next === 'function' ? next(items) : next; } });
    if (!cleanup) cleanup = effects[0]?.();
    return tree;
  }
  return { render, requests, pending, items: () => items, user: next => { user = next; render(); },
    replace: next => { items = next; render(); }, unmount: () => cleanup?.(),
    press() { const tree = render(); tree.props.children[0].props.onPress(); } };
}

test('load more fetches exactly one page and fences rapid duplicate taps', async () => {
  const f = fixture(); f.press(); f.press();
  assert.equal(f.requests.length, 1);
  f.pending.resolve(pagination.withNextPage([{ id: 2 }], 'talents/?cursor=last')); await flush();
  assert.deepEqual(Array.from(f.items(), row => row.id), [3, 2]);
  assert.equal(pagination.nextPage(f.items()), 'talents/?cursor=last');
  assert.equal(f.requests.length, 1, 'Never automatically drain all pages');
});

test('a refresh or account round trip cannot append an old page', async () => {
  for (const action of [f => f.replace([{ id: 9 }]), f => { f.user({ id: 2 }); f.user({ id: 1, role: 'ATHLETE' }); }, f => f.unmount()]) {
    const f = fixture(); f.press(); action(f);
    f.pending.resolve(pagination.withNextPage([{ id: 2 }], null)); await flush();
    assert.ok(!f.items().some(row => row.id === 2));
  }
});

test('a failed page remains retryable and does not discard loaded records', async () => {
  const f = fixture(); f.press(); f.pending.reject(new Error('Temporary failure')); await flush();
  assert.deepEqual(Array.from(f.items(), row => row.id), [3]);
  assert.ok(JSON.stringify(f.render()).includes('Temporary failure'));
  assert.equal(pagination.nextPage(f.items()), 'talents/?cursor=next');
});

test('local list edits keep continuation metadata while a refresh replaces it', () => {
  let state, update;
  const react = { useState(initial) { if (!state) state = initial; return [state, next => { state = typeof next === 'function' ? next(state) : next; }]; }, useCallback: fn => fn };
  [, update] = pagedState(react).usePagedState(pagination.withNextPage([{ id: 1 }], 'next'));
  update(rows => rows.map(row => ({ ...row, liked: true })));
  assert.equal(pagination.nextPage(state), 'next');
  update(pagination.withNextPage([{ id: 2 }], null));
  assert.equal(pagination.nextPage(state), null);
});
