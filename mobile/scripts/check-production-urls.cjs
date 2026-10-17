/* Read-only production checks. No login, uploads, mutations or publication. */
const path = require('node:path');
process.env.NODE_ENV ||= 'production';
require('@expo/env').load(path.resolve(__dirname, '..'));
const api = process.env.EXPO_PUBLIC_API_URL;
const checks = [
  ['API incoming calls', api && new URL('/api/messaging/calls/incoming/', api).href, [200, 401, 403]],
  ['API feed', api && new URL('/api/feed/posts/', api).href, [200, 401, 403]],
  ['API login route (GET must not create a session)', api && new URL('/api/auth/login/', api).href, [405]],
  ...['WEB', 'PRIVACY', 'TERMS', 'SUPPORT', 'DELETE_ACCOUNT'].map(key => [key, process.env[`EXPO_PUBLIC_${key}_URL`], [200]]),
];
(async () => {
  let failures = 0;
  for (const [name, value, expected] of checks) {
    try {
      if (!value) throw new Error('URL is not configured');
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('HTTPS without embedded credentials is required');
      const response = await fetch(url, { signal: AbortSignal.timeout(15000), redirect: 'follow' });
      if (new URL(response.url).protocol !== 'https:') throw new Error('Redirect downgraded HTTPS');
      const contentType = response.headers.get('content-type') || '';
      if (name.startsWith('API') && !contentType.includes('json')) throw new Error(`Expected API JSON, received ${response.status} ${contentType}`);
      if (!expected.includes(response.status)) throw new Error(`HTTP ${response.status}, expected ${expected.join('/')}`);
      if (['PRIVACY', 'TERMS', 'SUPPORT', 'DELETE_ACCOUNT'].includes(name)) {
        if (!contentType.includes('text/html')) throw new Error('Expected a public HTML page');
        const body = await response.text();
        if (!body.includes('Awinlink')) throw new Error('Public page must identify Awinlink');
        if (body.includes('Release information is awaiting completion')) throw new Error('Operator/contact configuration is incomplete');
      }
      console.log(`PASS ${name}: ${response.status} ${response.url}`);
      await response.body?.cancel();
    } catch (error) { failures++; console.log(`BLOCKED ${name}: ${error.message}`); }
  }
  console.log('Reachability does not verify policy accuracy, authenticated flows or service integrations.');
  process.exitCode = failures ? 1 : 0;
})().catch(error => { console.error(error.message); process.exitCode = 1; });
