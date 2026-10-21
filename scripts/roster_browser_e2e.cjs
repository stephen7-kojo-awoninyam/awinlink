/* Actual browser DOM -> session/CSRF HTTP -> isolated PostgreSQL roster fixtures. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.ok(['localhost', '127.0.0.1'].includes(new URL(fixture.origin).hostname));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
class CDP {
  constructor(url) {
    this.socket = new WebSocket(url); this.seq = 0; this.pending = new Map();
    this.ready = new Promise((resolve, reject) => { this.socket.onopen = resolve; this.socket.onerror = () => reject(Error('DevTools failed')); });
    this.socket.onmessage = event => { const message = JSON.parse(event.data), pending = this.pending.get(message.id);
      if (pending) { this.pending.delete(message.id); clearTimeout(pending.timer); message.error ? pending.reject(Error(message.error.message)) : pending.resolve(message.result); } };
  }
  async send(method, params = {}) {
    await this.ready;
    return new Promise((resolve, reject) => { const id = ++this.seq, timer = setTimeout(() => { this.pending.delete(id); reject(Error('DevTools timeout: ' + method)); }, 30000);
      this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params })); });
  }
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  async until(expression) {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) { if (await this.evaluate(expression)) return; await pause(80); }
    const feedback = await this.evaluate("document.querySelector('[data-feedback]')?.textContent || document.body.textContent.slice(0,300)");
    throw Error(`Browser condition timed out: ${expression}; ${feedback}`);
  }
  close() { this.socket.close(); }
}
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-roster-browser-'));
const chrome = spawn(process.env.ROSTER_TEST_CHROME, ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-extensions',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let browserDiagnostics = '';
chrome.stderr.on('data', data => { browserDiagnostics = (browserDiagnostics + data).slice(-4000); });
chrome.on('error', error => { console.error(error.message); process.exitCode = 1; });
const pages = []; let browser;
async function api(page, route, data, csrf = true) {
  return page.evaluate(`(async()=>{const r=await fetch(${JSON.stringify('/api/organizations/' + route)}, {${data ? "method:'POST',body:" + JSON.stringify(JSON.stringify(data)) + ',' : ''}
    headers:{'Content-Type':'application/json',${csrf ? "'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''," : ''}}});
    return {status:r.status,body:await r.json()};})()`);
}
async function refresh(page) { await page.evaluate("document.querySelector('[data-refresh]').click()"); }
async function choose(page) {
  await page.until(`!!document.querySelector('[data-workspace] option[value="${fixture.organization}"]')`);
  await page.evaluate(`(()=>{const s=document.querySelector('[data-workspace]');s.value='${fixture.organization}';s.dispatchEvent(new Event('change'));})()`);
}
async function create(page, values) {
  await page.evaluate(`(()=>{const f=document.querySelector('[data-create]');for(const[key,value]of Object.entries(${JSON.stringify(values)}))f.elements[key].value=value;f.requestSubmit();})()`);
}
const card = (scope, name) => `[...document.querySelectorAll('${scope} article')].find(c=>c.querySelector('h3')?.textContent===${JSON.stringify(name)})`;
async function action(page, scope, name, title) {
  await page.evaluate(`(()=>{const c=${card(scope, name)};[...c.querySelectorAll('button')].find(b=>b.textContent===${JSON.stringify(title)}).click();})()`);
}
(async () => {
  const deadline = Date.now() + 45000; let active;
  while (Date.now() < deadline) { try { active = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').trim().split(/\r?\n/); if (active.length === 2) break; } catch {} await pause(100); }
  assert.ok(active?.length === 2, `Headless browser did not start (exit ${chrome.exitCode}): ${browserDiagnostics}`);
  browser = new CDP(`ws://127.0.0.1:${active[0]}${active[1]}`);
  async function page(kind) {
    const context = await browser.send('Target.createBrowserContext');
    const target = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId: context.browserContextId });
    const p = new CDP(`ws://127.0.0.1:${active[0]}/devtools/page/${target.targetId}`); pages.push(p);
    await p.send('Page.enable'); await p.send('Network.enable');
    await p.send('Network.setBlockedURLs', { urls: ['https://*'] });
    await p.send('Network.setCookie', { name: fixture.cookie_name, value: fixture.sessions[kind], url: fixture.origin, httpOnly: true });
    await p.send('Page.navigate', { url: fixture.origin + '/organizations/talent-rosters/' });
    await p.until("!!document.querySelector('[data-refresh]') && !!document.querySelector('[data-mine] p')");
    return p;
  }
  const owner = await page('owner'), talent = await page('talent'), outsider = await page('outsider');
  await choose(owner);
  await owner.until("document.querySelectorAll('[data-roster] article').length===51");
  assert.equal((await api(outsider, `${fixture.organization}/roster/`)).status, 403);
  assert.equal((await api(owner, `${fixture.organization}/roster/`, { name: 'No CSRF', tag: 'Member' }, false)).status, 403);
  const name = 'Browser unclaimed <img src=x onerror=alert(1)> ✓';
  await create(owner, { name, tag: 'Web player ✓', roster: 'First team', talent_details: 'Forward', username: '' });
  await owner.until(`!!${card('[data-roster]', name)}`);
  assert.equal(await owner.evaluate(`${card('[data-roster]', name)}.querySelectorAll('img').length`), 0);
  assert.equal((await api(outsider, `${fixture.organization}/roster/public/`)).body.count, 0);
  await owner.evaluate(`${card('[data-roster]', name)}.querySelector('label input').value=${JSON.stringify(fixture.talent_username)}`);
  await action(owner, '[data-roster]', name, 'Request profile confirmation');
  await owner.until(`${card('[data-roster]', name)}?.textContent.includes('PENDING')`);
  await refresh(talent); await talent.until(`!!${card('[data-mine]', name)}`);
  await choose(talent); await talent.until(`!!${card('[data-roster]', name)}`);
  await api(owner, `${fixture.organization}/team/members/${fixture.talent_membership}/remove/`, {});
  await refresh(talent); await talent.until(`!!${card('[data-mine]', name)} && document.querySelector('[data-workspace]').options.length===1`);
  await action(talent, '[data-mine]', name, 'Confirm affiliation');
  await talent.until(`${card('[data-mine]', name)}?.textContent.includes('CONFIRMED')`);
  assert.equal((await api(outsider, `${fixture.organization}/roster/public/`)).body.count, 1);
  // Verify actual profile badge integration, not just the API representation.
  await outsider.send('Page.navigate', { url: fixture.origin + `/talents/profile/${fixture.talent_id}/` });
  await outsider.until("document.querySelector('[aria-label=\"Confirmed organization affiliations\"]')?.textContent.includes('Web player')");
  await outsider.send('Page.navigate', { url: fixture.origin + `/organizations/profile/${fixture.organization}/` });
  await outsider.until("document.querySelector('[aria-label=\"Confirmed organization affiliations\"]')?.textContent.includes('Web player')");
  await owner.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await refresh(owner); await owner.until(`!!${card('[data-roster]', name)}`);
  assert.equal(await owner.evaluate("(()=>{const f=document.querySelector('[data-create]'), r=f.getBoundingClientRect(), input=f.querySelector('[name=name]');return r.left>=0 && r.right<=innerWidth && input.getBoundingClientRect().height>=44;})()"), true, 'Mobile form must fit the viewport with usable controls');
  const artifacts = path.join(__dirname, '..', '.audit-roster-e2e'); fs.mkdirSync(artifacts, { recursive: true });
  const shot = await owner.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(path.join(artifacts, 'web-mobile-viewport.png'), Buffer.from(shot.data, 'base64'));
  await talent.evaluate('window.confirm=()=>false'); await action(talent, '[data-mine]', name, 'Remove tag');
  assert.equal((await api(owner, `${fixture.organization}/roster/public/`)).body.count, 1);
  await talent.evaluate('window.confirm=()=>true'); await action(talent, '[data-mine]', name, 'Remove tag');
  await talent.until(`${card('[data-mine]', name)}?.textContent.includes('REMOVED')`);
  await action(talent, '[data-mine]', name, 'View history');
  await talent.until(`${card('[data-mine]', name)}?.textContent.includes('CREATED') && ${card('[data-mine]', name)}?.textContent.includes('CONFIRM')`);
  assert.equal((await api(owner, `${fixture.organization}/roster/public/`)).body.count, 0);
  await create(owner, { name: 'Browser declined', tag: 'Alumni', roster: '', username: fixture.talent_username });
  await owner.until(`!!${card('[data-roster]', 'Browser declined')}`);
  await refresh(talent); await talent.until(`!!${card('[data-mine]', 'Browser declined')}`);
  await action(talent, '[data-mine]', 'Browser declined', 'Decline');
  await talent.until(`${card('[data-mine]', 'Browser declined')}?.textContent.includes('DECLINED')`);
  assert.equal((await api(owner, `${fixture.organization}/roster/public/`)).body.count, 0);
  await outsider.send('Page.reload');
  await outsider.until("!document.querySelector('[aria-label=\"Confirmed organization affiliations\"]') && !!document.querySelector('body')");
  console.log(JSON.stringify({ passed: true, checks: ['51-row pagination', 'unclaimed', 'XSS', 'CSRF', 'link', 'revocation', 'confirm', 'profile badges', '390px viewport', 'remove', 'history', 'decline'] }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(async () => {
  for (const page of pages) page.close();
  if (browser) { try { await browser.send('Browser.close'); } catch {} browser.close(); }
  if (chrome.exitCode === null) { await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), pause(3000)]); if (chrome.exitCode === null) chrome.kill(); }
  const target = path.resolve(profile);
  assert.equal(path.dirname(target), path.resolve(os.tmpdir())); assert.ok(path.basename(target).startsWith('awinlink-roster-browser-'));
  try { fs.rmSync(target, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
});
