const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const flush = () => new Promise(resolve => setImmediate(resolve));

function image(platform = 'ios') {
  let user = { id: 1, role: 'ATHLETE' }, state = null, effect, cleanup, dependencies, uri = '/media/portfolio/images/private.png';
  let resolveSource = async value => ({ uri: value, headers: { Authorization: `Bearer account-${user.id}` } });
  let ok = true;
  const requests = [], revoked = [], exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/components/AuthorizedImage.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, AbortController,
    fetch: async (url, options) => { requests.push({ url, ...options }); return { ok, blob: async () => 'bytes' }; },
    URL: { createObjectURL: () => 'blob:private-image', revokeObjectURL: value => revoked.push(value) },
    require: name => ({
      react: { useState: () => [state, value => { state = value; }], useEffect: (fn, deps) => {
        if (JSON.stringify(dependencies) !== JSON.stringify(deps)) { dependencies = deps; effect = fn; }
      } },
      'react/jsx-runtime': { jsx }, 'react-native': { Image: 'Image', Platform: { OS: platform } },
      '@/src/api/client': { mediaSource: value => resolveSource(value) },
      '@/src/auth/AuthProvider': { useAuth: () => ({ user }) },
    })[name],
  });
  const render = () => exports.AuthorizedImage({ uri });
  return { render, requests, revoked,
    commit() { render(); if (effect) { cleanup?.(); const next = effect; effect = null; cleanup = next(); } },
    account(id) { user = { ...user, id }; }, source(fn) { resolveSource = fn; }, deny() { ok = false; },
    unmount() { cleanup?.(); }, uri(value) { uri = value; },
  };
}

test('native portfolio image requests carry authorization and avoid cached sources', async () => {
  const view = image(); view.commit(); await flush();
  const source = view.render().props.source;
  assert.equal(source.headers.Authorization, 'Bearer account-1');
  assert.equal(source.cache, 'reload');
  view.account(2); assert.equal(view.render(), null); view.commit(); await flush();
  assert.equal(view.render().props.source.headers.Authorization, 'Bearer account-2');
});

test('web portfolio images fetch authenticated bytes and revoke their temporary URL', async () => {
  const view = image('web'); view.commit(); await flush();
  assert.equal(view.requests[0].headers.Authorization, 'Bearer account-1');
  assert.equal(view.render().props.source.uri, 'blob:private-image');
  view.unmount(); assert.deepEqual(view.revoked, ['blob:private-image']);
  assert.equal(view.requests[0].signal.aborted, true);
});

test('denied web images render no source', async () => {
  const view = image('web'); view.deny(); view.commit(); await flush();
  assert.equal(view.render(), null);
});

test('late image requests cannot restore the previous account or URI', async () => {
  for (const change of ['account', 'uri', 'unmount']) {
    const view = image(); let finish;
    view.source(() => new Promise(resolve => { finish = resolve; })); view.commit();
    const finishOld = finish;
    if (change === 'account') view.account(2);
    if (change === 'uri') view.uri('/media/portfolio/images/other.png');
    if (change === 'unmount') view.unmount(); else view.commit();
    finishOld({ uri: '/media/portfolio/images/late.png', headers: { Authorization: 'Bearer old' } });
    await flush(); assert.equal(view.render(), null);
  }
});
