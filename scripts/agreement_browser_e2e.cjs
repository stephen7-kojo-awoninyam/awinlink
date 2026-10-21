/* Real browser consent controls against synthetic PostgreSQL fixtures. */
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn } = require('node:child_process'); const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8')); assert.ok(['localhost', '127.0.0.1'].includes(new URL(fixture.origin).hostname));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.seq = 0; this.pending = new Map();
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = () => reject(Error('DevTools connection failed')); });
    this.ws.onmessage = e => { const msg = JSON.parse(e.data), p = this.pending.get(msg.id); if (p) { clearTimeout(p.timer); this.pending.delete(msg.id); msg.error ? p.reject(Error(msg.error.message)) : p.resolve(msg.result); } };
  }
  async send(method, params = {}) { await this.ready; return new Promise((resolve, reject) => { const id = ++this.seq;
    const timer = setTimeout(() => { this.pending.delete(id); reject(Error('DevTools timeout: ' + method)); }, 30000);
    this.pending.set(id, { resolve, reject, timer }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async evaluate(expression) { const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; }
  async until(expression) { const deadline = Date.now() + 30000; while (Date.now() < deadline) { if (await this.evaluate(expression)) return; await pause(80); }
    throw Error('Browser condition: ' + expression + '; ' + await this.evaluate("document.querySelector('[data-agreement-feedback]')?.textContent")); }
  close() { this.ws.close(); }
}
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-agreement-browser-'));
const chrome = spawn(process.env.AGREEMENT_TEST_CHROME, ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-extensions', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let diagnostics = ''; chrome.stderr.on('data', data => { diagnostics = (diagnostics + data).slice(-3000); });
chrome.on('error', error => { console.error(error.message); process.exitCode = 1; });
const pages = []; let browser;
const card = id => `document.querySelector('[data-agreement-id="${id}"]')`;
async function refresh(page) { await page.evaluate("document.querySelector('[data-agreement-refresh]').click()"); }
async function api(page, id) { return page.evaluate(`(async()=>{const r=await fetch('/api/organizations/agreements/${id}/');return {status:r.status,body:await r.json()};})()`); }
async function create(page, kind, title) {
  await page.evaluate(`(()=>{const f=document.querySelector('[data-agreement-create]');f.elements.roster_entry_id.value='${fixture.entry}';f.elements.roster_entry_id.dispatchEvent(new Event('change'));
    f.elements.kind.value=${JSON.stringify(kind)};f.elements.kind.dispatchEvent(new Event('change'));f.elements.title.value=${JSON.stringify(title)};f.elements.terms.value='Exact browser terms <img src=x onerror=alert(1)> ✓';
    if(${JSON.stringify(kind)}==='TRANSFER'){f.elements.destination_id.value='${fixture.destination}';f.elements.destination_tag.value='Player';f.elements.destination_roster.value='First team';}f.requestSubmit();})()`);
  await page.until(`[...document.querySelectorAll('[data-agreement-id]')].some(c=>c.querySelector('h3').textContent===${JSON.stringify(title)})`);
  return page.evaluate(`Number([...document.querySelectorAll('[data-agreement-id]')].find(c=>c.querySelector('h3').textContent===${JSON.stringify(title)}).dataset.agreementId)`);
}
async function sign(page, id, action, party, reason = '') {
  await page.until(`!!${card(id)}?.querySelector('[data-action=${action}][data-party=${party}]')`);
  await page.evaluate(`(()=>{const c=${card(id)}, check=c.querySelector('input[type=checkbox]');if(check){check.checked=true;check.dispatchEvent(new Event('change'));}
    const reason=c.querySelector('label:not(.agreement-consent) input');if(reason){reason.value=${JSON.stringify(reason)};reason.dispatchEvent(new Event('input'));}
    const b=c.querySelector('[data-action=${action}][data-party=${party}]');if(b.disabled)throw Error('Action disabled');b.click();})()`);
}
(async () => {
  let active; const deadline = Date.now() + 45000;
  while (Date.now() < deadline) { try { active = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').trim().split(/\r?\n/); if (active.length === 2) break; } catch {} await pause(100); }
  assert.ok(active?.length === 2, diagnostics || 'Chrome did not start'); browser = new CDP(`ws://127.0.0.1:${active[0]}${active[1]}`);
  async function page(user) { const context = await browser.send('Target.createBrowserContext'), target = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId: context.browserContextId });
    const p = new CDP(`ws://127.0.0.1:${active[0]}/devtools/page/${target.targetId}`); pages.push(p); await p.send('Page.enable'); await p.send('Network.enable');
    await p.send('Network.setBlockedURLs', { urls: ['https://*'] }); await p.send('Network.setCookie', { name: fixture.cookie_name, value: fixture.sessions[user], url: fixture.origin, httpOnly: true });
    await p.send('Page.navigate', { url: fixture.origin + '/organizations/agreements/' });
    await p.until("!!document.querySelector('[data-agreement-list] p')"); return p; }
  const origin = await page('origin'), talent = await page('talent'), destination = await page('destination'), outsider = await page('outsider');
  let contract;
  for (const kind of ['CONTRACT', 'SPONSORSHIP', 'AMBASSADOR']) {
    const id = await create(origin, kind, kind + ' browser');
    assert.equal((await api(talent, id)).status, 404);
    assert.equal(await origin.evaluate(`${card(id)}.querySelector('[data-action=SUBMIT]').disabled`), true);
    assert.equal(await origin.evaluate(`${card(id)}.querySelector('pre').querySelectorAll('img').length`), 0);
    await sign(origin, id, 'SUBMIT', 'ORIGIN'); await origin.until(`${card(id)}?.textContent.includes('PENDING')`);
    assert.equal((await api(outsider, id)).status, 404); assert.equal((await api(destination, id)).status, 404);
    if (kind === 'CONTRACT') {
      await origin.evaluate(`(()=>{const c=${card(id)};[...c.querySelectorAll('button')].find(b=>b.textContent.startsWith('Revise terms')).click();const f=c.querySelector('form');f.elements.terms.value='Revised exact browser contract';f.requestSubmit();})()`);
      await origin.until(`${card(id)}?.textContent.includes('Revision 2') && ${card(id)}?.textContent.includes('DRAFT')`);
      await sign(origin, id, 'SUBMIT', 'ORIGIN'); await origin.until(`${card(id)}?.textContent.includes('PENDING')`);
      contract = id;
    }
    await refresh(talent); await talent.until(`!!${card(id)}?.querySelector('[data-action=ACCEPT]')`);
    await sign(talent, id, 'ACCEPT', 'TALENT'); await talent.until(`${card(id)}?.textContent.includes('ACTIVE')`);
  }
  await sign(talent, contract, 'REQUEST_END', 'TALENT', 'Campaign completed'); await talent.until(`${card(contract)}?.textContent.includes('ENDING')`);
  await refresh(origin); await origin.until(`${card(contract)}?.textContent.includes('Campaign completed')`);
  await sign(origin, contract, 'ACCEPT_END', 'ORIGIN'); await origin.until(`${card(contract)}?.textContent.includes('ENDED')`);
  const transfer = await create(origin, 'TRANSFER', 'Browser transfer'); await sign(origin, transfer, 'SUBMIT', 'ORIGIN'); await origin.until(`${card(transfer)}?.textContent.includes('PENDING')`);
  await refresh(talent); await talent.until(`!!${card(transfer)}?.querySelector('[data-action=ACCEPT]')`); await sign(talent, transfer, 'ACCEPT', 'TALENT'); await talent.until(`${card(transfer)}?.textContent.includes('PENDING') && !${card(transfer)}?.querySelector('[data-action=ACCEPT]')`);
  await refresh(destination); await destination.until(`!!${card(transfer)}?.querySelector('[data-action=ACCEPT]')`);
  await sign(destination, transfer, 'ACCEPT', 'DESTINATION'); await destination.until(`${card(transfer)}?.textContent.includes('COMPLETED')`);
  await destination.evaluate(`[...${card(transfer)}.querySelectorAll('button')].find(b=>b.textContent==='View agreement history').click()`);
  await destination.until(`${card(transfer)}?.textContent.includes('TRANSFER_COMPLETED')`);
  await origin.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }); await refresh(origin);
  await origin.until(`!!${card(transfer)}`);
  assert.equal(await origin.evaluate("document.querySelector('[data-agreements]').getBoundingClientRect().right<=innerWidth"), true);
  const artifacts = path.join(__dirname, '..', '.audit-agreement-e2e'); fs.mkdirSync(artifacts, { recursive: true });
  const shot = await origin.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); fs.writeFileSync(path.join(artifacts, 'mobile-width.png'), Buffer.from(shot.data, 'base64'));
  console.log(JSON.stringify({ passed: true, checks: ['all types', 'explicit consent controls', 'private drafts', 'revision reset', 'mutual ending', 'three-party transfer', 'history', '390px viewport'] }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(async () => {
  pages.forEach(p => p.close()); if (browser) { try { await browser.send('Browser.close'); } catch {} browser.close(); }
  if (chrome.exitCode === null) { await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), pause(3000)]); if (chrome.exitCode === null) chrome.kill(); }
  const target = path.resolve(profile); assert.equal(path.dirname(target), path.resolve(os.tmpdir())); assert.ok(path.basename(target).startsWith('awinlink-agreement-browser-'));
  try { fs.rmSync(target, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
});
