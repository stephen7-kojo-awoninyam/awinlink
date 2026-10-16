/* Real HTTP/Channels/Redis/WebRTC audit, using only synthetic capture devices. */
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const artifacts = path.join(root, '.audit-vc-e2e');
const fixture = JSON.parse(fs.readFileSync(path.join(artifacts, 'fixture.json')));
const chromePath = process.env.CLASSROOM_TEST_CHROME;
if (!chromePath) throw new Error('Set CLASSROOM_TEST_CHROME to an installed Chrome binary.');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const evidence = { synthetic_capture: true, real_rtc_engine: true, two_asgi_workers: true,
  database: 'PostgreSQL 17.11', redis: 'Redis 8.10.2 Windows port', checks: [], unverified: ['physical devices', 'native Android/iOS RTC', 'forced TURN relay', 'provider push delivery'] };
const note = (name, detail) => { evidence.checks.push({ name, passed: true, detail }); console.log('PASS:', name); };
class CDP {
  constructor(url) { this.socket = new WebSocket(url); this.seq = 0; this.pending = new Map(); this.listeners = new Map();
    this.open = new Promise((resolve, reject) => { this.socket.onopen = resolve; this.socket.onerror = event => reject(new Error(`CDP WebSocket failed: ${event.message || event.type}`)); });
    this.socket.onmessage = event => { const message = JSON.parse(event.data);
      if (message.id) { const pending = this.pending.get(message.id); if (pending) { this.pending.delete(message.id); clearTimeout(pending.timer); message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result); } }
      else for (const listener of this.listeners.get(message.method) || []) listener(message.params);
    };
  }
  async send(method, params = {}) { await this.open; return new Promise((resolve, reject) => {
    const id = ++this.seq; const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`CDP timeout after 60 seconds: ${method}`)); }, 60000);
    this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params }));
  }); }
  on(name, listener) { if (!this.listeners.has(name)) this.listeners.set(name, []); this.listeners.get(name).push(listener); }
  async evaluate(expression) { const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  async until(expression, timeout = 30000) { const deadline = Date.now() + timeout; let last;
    while (Date.now() < deadline) { try { last = await this.evaluate(expression); if (last) return last; } catch (error) { last = error.message; } await pause(100); }
    throw new Error(`Condition timed out: ${expression}; last=${JSON.stringify(last)}`);
  }
  close() { for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('CDP closed')); } this.pending.clear(); this.socket.close(); }
}
const profile = fs.mkdtempSync(path.join(artifacts, 'chrome-'));
const chromeLog = fs.openSync(path.join(artifacts, 'chrome.log'), 'a');
const chrome = spawn(chromePath, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--disable-sync', '--disable-component-update', '--remote-debugging-port=0',
  '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required',
  `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', chromeLog, chromeLog] });
fs.closeSync(chromeLog);
const pages = []; let browser;
async function makePage(identity, port, width = 1440) {
  const context = await browser.send('Target.createBrowserContext');
  const target = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId: context.browserContextId });
  const active = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').trim().split(/\r?\n/);
  const cdp = new CDP(`ws://127.0.0.1:${active[0]}/devtools/page/${target.targetId}`); await cdp.open;
  pages.push(cdp); await cdp.send('Runtime.enable'); await cdp.send('Page.enable'); await cdp.send('Network.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 500 });
  cdp.on('Page.javascriptDialogOpening', () => void cdp.send('Page.handleJavaScriptDialog', { accept: true }));
  const origin = `http://127.0.0.1:${port}`;
  await cdp.send('Network.setCookie', { name: fixture.cookie_name, value: fixture.identities[identity].session_cookie, url: origin, httpOnly: true, sameSite: 'Lax' });
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    window.__vcPCs=[];window.__vcSockets=[];window.__vcStreams=[];
    const RealPC=window.RTCPeerConnection;window.RTCPeerConnection=class extends RealPC{constructor(...args){super(...args);__vcPCs.push(this);}};
    const RealSocket=window.WebSocket;window.WebSocket=class extends RealSocket{constructor(...args){super(...args);__vcSockets.push(this);}};
    const capture=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async options=>{const stream=await capture(options);__vcStreams.push(stream);return stream;};
  ` });
  await cdp.send('Page.navigate', { url: `${origin}/learning/sessions/${fixture.session_id}/classroom/` });
  await cdp.until(`!!document.getElementById('vc-status') && document.getElementById('vc-status').textContent.includes('LIVE')`);
  return cdp;
}
const get = (page, suffix) => page.evaluate(`fetch('/api/learning/sessions/${fixture.session_id}/${suffix}',{credentials:'same-origin'}).then(async r=>({status:r.status,body:await r.json()}))`);
const post = (page, suffix, body) => page.evaluate(`fetch('/api/learning/sessions/${fixture.session_id}/${suffix}',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:${JSON.stringify(JSON.stringify(body))}}).then(async r=>({status:r.status,body:await r.json()}))`);
async function stats(page) { return page.evaluate(`(async()=>{const result=[];for(const pc of __vcPCs.filter(p=>p.connectionState==='connected')){const data=await pc.getStats();const inbound=[...data.values()].filter(s=>s.type==='inbound-rtp').map(s=>({kind:s.kind,bytes:s.bytesReceived,frames:s.framesDecoded}));const pair=[...data.values()].find(s=>s.type==='candidate-pair'&&s.state==='succeeded'&&s.nominated);result.push({inbound,localCandidate:pair?data.get(pair.localCandidateId)?.candidateType:null,remoteCandidate:pair?data.get(pair.remoteCandidateId)?.candidateType:null});}return result;})()`); }
async function rtp(page) { const deadline = Date.now() + 30000; while (Date.now() < deadline) { const result = await stats(page);
  if (result.some(p => p.inbound.some(s => s.kind === 'video' && s.bytes > 0 && s.frames > 0) && p.inbound.some(s => s.kind === 'audio' && s.bytes > 0))) return result;
  await pause(200);
} throw new Error('Real inbound audio/video RTP did not arrive'); }
async function draw(page, kind, text) {
  await page.evaluate(`document.getElementById('vc-board').scrollIntoView({block:'center'});document.getElementById('vc-tool').value=${JSON.stringify(kind)};document.getElementById('vc-board-text').value=${JSON.stringify(text || '')};`);
  const rect = await page.evaluate(`(()=>{const r=document.getElementById('vc-board').getBoundingClientRect();return {x:r.left+r.width*.2,y:r.top+r.height*.2,w:r.width,h:r.height};})()`);
  await page.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
  if (kind !== 'text') await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rect.x + rect.w * .2, y: rect.y + rect.h * .15, button: 'left', buttons: 1 });
  await page.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rect.x + (kind === 'text' ? 0 : rect.w * .2), y: rect.y + (kind === 'text' ? 0 : rect.h * .15), button: 'left', clickCount: 1 });
}
(async () => {
  const deadline = Date.now() + 20000;
  while (!fs.existsSync(path.join(profile, 'DevToolsActivePort'))) { if (Date.now() > deadline || chrome.exitCode !== null) throw new Error('Chrome DevTools did not start'); await pause(100); }
  const active = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').trim().split(/\r?\n/);
  browser = new CDP(`ws://127.0.0.1:${active[0]}${active[1]}`); await browser.open;
  const host = await makePage('host', 18765), learner = await makePage('learner', 18766, 390), waiting = await makePage('waiting', 18766, 390);
  assert.equal(await waiting.evaluate(`document.getElementById('vc-join').disabled`), true);
  const denied = await post(waiting, 'join/', { connection_id: crypto.randomUUID() }); assert.equal(denied.status, 403);
  note('Waiting learner cannot join through UI or direct API');
  for (const page of [host, learner]) await page.evaluate(`document.getElementById('vc-join').click()`);
  for (const page of [host, learner]) await page.until(`document.getElementById('vc-status').textContent.includes('Connected') && !document.getElementById('vc-message').disabled`);
  const hostStats = await rtp(host), learnerStats = await rtp(learner);
  note('Real audio/video RTP across two ASGI workers and Redis', { host: hostStats, learner: learnerStats });
  assert.equal(await learner.evaluate(`document.documentElement.scrollWidth<=innerWidth+1`), true);
  note('Browser participant grid at 390px viewport');
  const drawDenied = await post(learner, 'whiteboard/', { operation_id: crypto.randomUUID(), base_revision: 0, action: 'clear', payload: {} }); assert.equal(drawDenied.status, 403);
  await draw(host, 'text', 'VC synchronized note');
  await learner.until(`document.getElementById('vc-board-content').textContent.includes('VC synchronized note')`);
  note('Whiteboard host drawing synchronized; learner editing denied by server');
  await host.evaluate(`(()=>{const row=[...document.querySelectorAll('.vc-roster-row')].find(r=>r.textContent.includes(${JSON.stringify(fixture.identities.learner.username)}));[...row.querySelectorAll('button')].find(b=>b.textContent==='Allow drawing').click();})()`);
  await learner.until(`!document.getElementById('vc-tool').disabled`);
  const before = Object.keys((await get(host, 'whiteboard/')).body.objects).length;
  await draw(learner, 'rectangle');
  await host.until(`document.querySelectorAll('#vc-board-content li').length>${before}`);
  await learner.evaluate(`document.getElementById('vc-undo').click()`);
  await host.until(`document.querySelectorAll('#vc-board-content li').length===${before}`);
  note('Host editing grant, learner shape and synchronized undo');
  const message = 'VC hello <img src=x onerror="window.vcInjected=true">';
  await host.evaluate(`document.getElementById('vc-message').value=${JSON.stringify(message)};document.getElementById('vc-chat-form').dispatchEvent(new Event('submit',{cancelable:true}));`);
  await learner.until(`document.getElementById('vc-chat').textContent.includes(${JSON.stringify(message)})`);
  assert.equal(await learner.evaluate(`!!document.querySelector('#vc-chat img') || !!window.vcInjected`), false);
  note('Persisted chat fan-out and safe HTML rendering');
  const isolated = await learner.evaluate(`fetch('/api/learning/sessions/${fixture.other_session_id}/whiteboard/').then(r=>r.status)`);
  assert.equal(isolated, 403); note('Other session whiteboard is isolated');
  const firstUuid = await learner.evaluate(`new URL(__vcSockets.find(s=>s.url.includes('connection_id=')&&s.readyState===1).url).searchParams.get('connection_id')`);
  await learner.evaluate(`__vcSockets.find(s=>s.url.includes('connection_id=')&&s.readyState===1).close()`);
  await learner.until(`__vcSockets.some(s=>s.url.includes('connection_id=')&&s.readyState===1&&new URL(s.url).searchParams.get('connection_id')!==${JSON.stringify(firstUuid)}) && document.getElementById('vc-status').textContent.includes('Connected')`);
  await rtp(learner); await learner.until(`document.getElementById('vc-chat').textContent.includes(${JSON.stringify(message)}) && document.getElementById('vc-board-content').textContent.includes('VC synchronized note')`);
  const intervals = (await get(host, 'attendance/')).body.results;
  assert.equal(intervals.filter(row => row.user === fixture.identities.learner.user_id && row.left_at === null).length, 1);
  note('Fresh reconnect UUID, RTP recovery, persisted chat/board and one open attendance interval');
  await host.evaluate(`(()=>{const row=[...document.querySelectorAll('.vc-roster-row')].find(r=>r.textContent.includes(${JSON.stringify(fixture.identities.learner.username)}));[...row.querySelectorAll('button')].find(b=>b.textContent==='Revoke drawing').click();})()`);
  await learner.until(`document.getElementById('vc-tool').disabled`);
  note('Editing revocation reaches connected learner');
  await host.evaluate(`(()=>{const row=[...document.querySelectorAll('.vc-roster-row')].find(r=>r.textContent.includes(${JSON.stringify(fixture.identities.waiting.username)}));[...row.querySelectorAll('button')].find(b=>b.textContent==='Admit').click();})()`);
  await waiting.until(`!document.getElementById('vc-join').disabled`); note('Host admission unlocks waiting browser through server state');
  await host.evaluate(`(()=>{const row=[...document.querySelectorAll('.vc-roster-row')].find(r=>r.textContent.includes(${JSON.stringify(fixture.identities.learner.username)}));[...row.querySelectorAll('button')].find(b=>b.textContent==='Remove').click();})()`);
  await learner.until(`__vcStreams.length>0 && __vcStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended')) && !document.getElementById('vc-status').textContent.includes('Connected')`);
  assert.equal((await get(learner, 'chat/')).status, 403); note('Removal closes real capture and denies chat reads');
  await host.evaluate(`document.querySelector('[data-action=end]').click()`);
  await host.until(`__vcStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended')) && document.getElementById('vc-status').textContent.includes('ENDED')`);
  const ended = (await get(host, 'attendance/')).body.results; assert.ok(ended.every(row => row.left_at !== null));
  note('Session ending stops capture and closes all attendance');
  evidence.success = true;
})().catch(error => { evidence.success = false; evidence.error = error.message; console.error(error); process.exitCode = 1; }).finally(async () => {
  fs.writeFileSync(path.join(artifacts, 'browser-e2e.json'), JSON.stringify(evidence, null, 2));
  if (browser) await browser.send('Browser.close').catch(() => {});
  for (const page of pages) page.close(); browser?.close();
  await pause(300); if (chrome.exitCode === null) chrome.kill();
});
