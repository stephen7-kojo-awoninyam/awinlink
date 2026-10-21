/* Real browser controls -> loopback Django -> PostgreSQL. Fixtures arrive on stdin. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
const origin = new URL(fixture.origin);
assert.ok(['localhost', '127.0.0.1'].includes(origin.hostname));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
class CDP {
  constructor(url) {
    this.socket = new WebSocket(url); this.seq = 0; this.pending = new Map();
    this.ready = new Promise((resolve, reject) => { this.socket.onopen = resolve; this.socket.onerror = () => reject(Error('DevTools connection failed')); });
    this.socket.onmessage = event => {
      const message = JSON.parse(event.data), pending = this.pending.get(message.id);
      if (pending) { this.pending.delete(message.id); clearTimeout(pending.timer); message.error ? pending.reject(Error(message.error.message)) : pending.resolve(message.result); }
    };
  }
  async send(method, params = {}) {
    await this.ready;
    return new Promise((resolve, reject) => {
      const id = ++this.seq, timer = setTimeout(() => { this.pending.delete(id); reject(Error('DevTools timeout: ' + method)); }, 30000);
      this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  async until(expression) {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) { if (await this.evaluate(expression)) return; await pause(100); }
    throw Error('Browser condition timed out: ' + expression);
  }
  close() { this.socket.close(); }
}
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-market-browser-'));
const chrome = spawn(process.env.TALENT_MARKET_TEST_CHROME, ['--headless=new', '--disable-gpu', '--disable-background-networking',
  '--disable-extensions', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { windowsHide: true, stdio: 'ignore' });
const pages = []; let browser;
chrome.on('error', error => { console.error(error.message); process.exitCode = 1; });
async function api(page, path, data) {
  const options = data ? { method: 'POST', body: JSON.stringify(data) } : {};
  return page.evaluate(`(async()=>{const r=await fetch(${JSON.stringify('/api/marketplace/' + path)},
    {...${JSON.stringify(options)},headers:{'Content-Type':'application/json','X-CSRFToken':document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]}});
    return {status:r.status,body:await r.json()};})()`);
}
async function form(page, id, values) {
  await page.evaluate(`(()=>{const f=document.getElementById(${JSON.stringify(id)});for(const [key,value]of Object.entries(${JSON.stringify(values)})){const el=f.elements[key];if(el.type==='checkbox')el.checked=value;else el.value=value;}f.requestSubmit();})()`);
}
async function openDeals(page, id) {
  await page.evaluate("document.getElementById('deals').click()");
  await page.until(`[...document.querySelectorAll('#results button')].some(b=>b.textContent.startsWith('Offer #${id} '))`);
  await page.evaluate(`[...document.querySelectorAll('#results button')].find(b=>b.textContent.startsWith('Offer #${id} ')).click()`);
  await page.until("!document.getElementById('room').hidden");
}
(async () => {
  const deadline = Date.now() + 20000; let active;
  while (Date.now() < deadline) {
    try { active = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').trim().split(/\r?\n/); if (active.length === 2) break; } catch {}
    await pause(100);
  }
  assert.ok(active?.length === 2, 'Chrome DevTools did not start');
  browser = new CDP(`ws://127.0.0.1:${active[0]}${active[1]}`);
  async function page(kind) {
    const context = await browser.send('Target.createBrowserContext');
    const target = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId: context.browserContextId });
    const page = new CDP(`ws://127.0.0.1:${active[0]}/devtools/page/${target.targetId}`); pages.push(page);
    await page.send('Page.enable'); await page.send('Network.enable');
    await page.send('Network.setBlockedURLs', { urls: ['https://*'] });
    await page.send('Network.setCookie', { name: fixture.cookie_name, value: fixture.sessions[kind], url: fixture.origin, httpOnly: true });
    await page.send('Page.navigate', { url: fixture.origin + '/marketplace/' });
    await page.until("!!document.querySelector('#search select option')");
    return page;
  }
  const talent = await page('talent'), scout = await page('scout'), outsider = await page('outsider');
  const appointment = new Date(Date.now() + 3600000).toISOString();
  await form(talent, 'listing', { title: 'Browser talent \u2713', description: 'Browser workflow', ecosystem: 'SPORTS',
    subecosystem: fixture.domain_id, status: 'PUBLISHED', consent: true,
    ...(fixture.phase_two ? { booking_enabled: true, pricing_mode: 'FIXED', base_price: '42.50', duration_minutes: 60 } : {}) });
  await talent.until("document.getElementById('results').textContent.includes('Browser talent')");
  const listing = (await api(scout, 'listings/?q=Browser')).body.results[0]; assert.ok(listing);
  if (fixture.phase_two) {
    await talent.send('Page.navigate', { url: fixture.origin + '/marketplace/bookings/' });
    await talent.until("document.getElementById('market-bookings')?.getAttribute('aria-busy')==='false'");
    await form(talent, 'availability-form', { starts_at: appointment, ends_at: new Date(Date.parse(appointment) + 7200000).toISOString(), timezone: 'UTC' });
    await talent.until("document.getElementById('availability-results').textContent.includes('UTC')");
    await talent.send('Page.navigate', { url: fixture.origin + '/marketplace/' });
    await talent.until("!!document.querySelector('#search select option')");
    const openings = await api(scout, `availability/?listing=${listing.id}`); assert.ok(openings.body.results.length);
  }
  await form(scout, 'offer', { listing: listing.id, terms: 'Exact browser terms',
    ...(fixture.phase_two ? { starts_at: appointment, expected_revision: listing.revision } : {}) });
  await scout.until("document.getElementById('terms').textContent.includes('Exact browser terms')");
  const offer = (await api(scout, 'offers/')).body.results[0];
  assert.equal(await scout.evaluate("document.querySelector('[data-action=ACCEPT]').hidden"), true);
  await form(scout, 'message', { body: 'Browser hello \ud83d\udc4b' });
  await scout.until("document.getElementById('messages').textContent.includes('Browser hello')");
  for (let i = 0; i < 52; i++) assert.equal((await api(scout, `deals/${offer.id}/messages/`, { body: 'History ' + i })).status, 201);
  await openDeals(talent, offer.id);
  await talent.until("!document.getElementById('older-messages').hidden");
  await talent.evaluate("document.getElementById('older-messages').click()");
  await talent.until("document.getElementById('messages').textContent.includes('Browser hello')");
  assert.equal(await talent.evaluate("document.getElementById('older-messages').hidden"), true);
  await form(talent, 'message', { body: 'Browser reply \u2713' });
  await talent.until("document.getElementById('messages').textContent.includes('Browser reply')");
  assert.equal((await api(outsider, `deals/${offer.id}/`)).status, 403);
  await talent.evaluate("document.getElementById('accept-consent').checked=true;document.querySelector('[data-action=ACCEPT]').click()");
  await talent.until("document.getElementById('terms').textContent.includes('ACCEPTED')");
  assert.equal(await talent.evaluate("getComputedStyle(document.getElementById('message')).display"), 'none');
  await openDeals(scout, offer.id);
  await scout.until("document.getElementById('terms').textContent.includes('ACCEPTED')");
  assert.equal((await api(scout, `deals/${offer.id}/messages/`, { body: 'After acceptance' })).status, 400);
  for (const page of pages) assert.equal(await page.evaluate("document.getElementById('notice').textContent"), '');
  if (fixture.phase_two) {
    const accepted = (await api(scout, `deals/${offer.id}/`)).body.offer;
    assert.ok(accepted.booking_id); assert.equal(accepted.quoted_amount, '42.50');
    const route = fixture.origin + '/marketplace/bookings/?booking=' + accepted.booking_id;
    await scout.send('Page.navigate', { url: route });
    await scout.until("document.getElementById('booking-title')?.textContent.includes('Booking #') && document.getElementById('market-bookings').getAttribute('aria-busy')==='false'");
    await form(scout, 'booking-message-form', { body: 'Fulfillment channel' });
    await scout.until("document.getElementById('booking-messages').textContent.includes('Fulfillment channel')");
    assert.equal((await api(outsider, `bookings/${accepted.booking_id}/`)).status, 403);
    await scout.until("document.getElementById('market-bookings').getAttribute('aria-busy')==='false'");
    await scout.evaluate("document.getElementById('booking-reason').value='Release appointment';[...document.querySelectorAll('#booking-actions button')].find(b=>b.textContent==='Cancel booking').click()");
    await scout.until("document.getElementById('booking-summary').textContent.includes('CANCELLED')");
    assert.equal(await scout.evaluate("getComputedStyle(document.getElementById('booking-message-form')).display"), 'none');
    assert.equal(await scout.evaluate("document.getElementById('booking-error').textContent"), '');
  }
  console.log(JSON.stringify({ passed: true, checks: ['listing publication', 'offer', 'two-way Unicode messaging', 'older history', 'acceptance', 'final read-only UI', 'outsider denial', 'final write denial'] }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(async () => {
  for (const page of pages) page.close();
  if (browser) { try { await browser.send('Browser.close'); } catch {} browser.close(); }
  if (chrome.exitCode === null) { await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), pause(3000)]); if (chrome.exitCode === null) chrome.kill(); }
  assert.equal(path.dirname(profile), path.resolve(os.tmpdir()));
  assert.ok(path.basename(profile).startsWith('awinlink-market-browser-'));
  try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
});
