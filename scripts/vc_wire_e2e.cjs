/* Real Daphne socket close-code checks using the existing local audit fixture. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const WebSocket = require(require.resolve('ws', { paths: [path.join(root, 'mobile')] }));
const artifacts = path.join(root, '.audit-vc-e2e');
const fixture = JSON.parse(fs.readFileSync(path.join(artifacts, 'fixture.json')));
const origin = 'http://127.0.0.1:18765';
const result = { real_daphne_transport: true, checks: [], success: false };
(async () => {
  let cookie = `${fixture.cookie_name}=${fixture.identities.host.session_cookie}`;
  const page = await fetch(origin + '/learning/classrooms/', { headers: { Cookie: cookie } });
  assert.equal(page.status, 200);
  const html = await page.text();
  const token = html.match(/name="csrfmiddlewaretoken" value="([^"]+)"/)?.[1];
  assert.ok(token, 'CSRF token must be issued by the real page');
  const csrfCookie = page.headers.getSetCookie().find(value => value.startsWith('csrftoken='));
  if (csrfCookie) cookie += '; ' + csrfCookie.split(';')[0];
  for (const activity of [true, false]) for (const binary of [true, false]) {
    const connection = randomUUID();
    if (!activity) {
      const joined = await fetch(`${origin}/api/learning/sessions/${fixture.session_id}/join/`, {
        method: 'POST', headers: { Cookie: cookie, 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ connection_id: connection }),
      });
      assert.equal(joined.status, 200, await joined.text());
    }
    const endpoint = activity ? `/ws/learning/sessions/${fixture.session_id}/whiteboard/` : `/ws/learning/sessions/${fixture.session_id}/?connection_id=${connection}`;
    const code = await new Promise((resolve, reject) => {
      const socket = new WebSocket(origin.replace('http:', 'ws:') + endpoint, { headers: { Cookie: cookie, Origin: origin } });
      const timer = setTimeout(() => { socket.terminate(); reject(new Error('Protocol close timed out')); }, 15000);
      socket.once('open', () => socket.send(binary ? Buffer.from([1, 2, 3]) : 'x'.repeat(65537)));
      socket.once('close', value => { clearTimeout(timer); resolve(value); });
      socket.once('error', error => { clearTimeout(timer); reject(error); });
    });
    assert.equal(code, 4400);
    const name = `${activity ? 'Whiteboard' : 'Signaling'} rejects ${binary ? 'binary' : 'oversized'} frame`;
    result.checks.push({ name, code, passed: true }); console.log('PASS:', name);
  }
  result.success = true;
})().catch(error => { result.error = error.message; console.error(error.message); process.exitCode = 1; }).finally(() => {
  fs.writeFileSync(path.join(artifacts, 'wire-close-e2e.json'), JSON.stringify(result, null, 2));
});
