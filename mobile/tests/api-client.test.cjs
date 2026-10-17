const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function client(fetch) {
  const tokens = new Map([['awinlink.access-token', 'expired'], ['awinlink.refresh-token', 'refresh']]);
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/api/client.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInNewContext(source, {
    exports, URL, Headers, FormData, fetch, process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example' } },
    require: () => ({
      getItemAsync: async key => tokens.get(key) || null,
      setItemAsync: async (key, value) => tokens.set(key, value),
      deleteItemAsync: async key => tokens.delete(key),
    }),
  });
  return { ...exports, tokens };
}

test('concurrent expired requests share refresh and preserve rotated refresh token', async () => {
  let refreshes = 0;
  const api = client(async (url, options) => {
    if (url.endsWith('auth/refresh/')) {
      refreshes++;
      await new Promise(resolve => setTimeout(resolve, 10));
      return Response.json({ access: 'new-access', refresh: 'rotated' });
    }
    return options.headers.get('Authorization') === 'Bearer new-access'
      ? Response.json({ ok: true }) : Response.json({ detail: 'expired' }, { status: 401 });
  });
  const results = await Promise.all([api.apiRequest('feed/posts/'), api.apiRequest('notifications/')]);
  assert.equal(refreshes, 1);
  assert.ok(results.every(result => result.ok));
  assert.equal(api.tokens.get('awinlink.refresh-token'), 'rotated');
});

test('logout during refresh cannot resurrect the old session', async () => {
  let release;
  let started;
  const pending = new Promise(resolve => { started = resolve; });
  const api = client(async url => {
    if (url.endsWith('auth/refresh/')) {
      started();
      await new Promise(resolve => { release = resolve; });
      return Response.json({ access: 'stale' });
    }
    return Response.json({ detail: 'expired' }, { status: 401 });
  });
  const request = api.apiRequest('notifications/');
  await pending;
  await api.clearTokens();
  release();
  await assert.rejects(request, error => error.status === 401);
  assert.equal(api.tokens.size, 0);
});

test('invalid refresh clears credentials and does not loop', async () => {
  let calls = 0;
  const api = client(async () => { calls++; return Response.json({ detail: 'invalid' }, { status: 401 }); });
  await assert.rejects(api.apiRequest('notifications/'), error => error.status === 401);
  assert.equal(calls, 2);
  assert.equal(api.tokens.size, 0);
});

test('late invalid refresh cannot clear credentials from a new login', async () => {
  let release, started;
  const pending = new Promise(resolve => { started = resolve; });
  const api = client(async url => {
    if (url.endsWith('auth/refresh/')) {
      started(); await new Promise(resolve => { release = resolve; });
    }
    return Response.json({ detail: 'expired' }, { status: 401 });
  });
  const request = api.apiRequest('notifications/');
  await pending;
  await api.storeTokens('new-login', 'new-refresh');
  release();
  await assert.rejects(request, error => error.status === 401);
  assert.equal(api.tokens.get('awinlink.access-token'), 'new-login');
  assert.equal(api.tokens.get('awinlink.refresh-token'), 'new-refresh');
});
