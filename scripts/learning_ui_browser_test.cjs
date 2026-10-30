/* Real Chrome layout/keyboard checks on generated, offline Learning fixtures. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn, execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const output = path.join(root, '.audit-learning-ui');
const chromePath = process.env.LEARNING_TEST_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const studioOnly = process.argv.includes('--studio-only');
const studioKeyboardOnly = process.argv.includes('--studio-keyboard');
const quizOnly = process.argv.includes('--quiz-only');
const lessonOnly = process.argv.includes('--lesson-only');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const profile = fs.mkdtempSync(path.join(output, 'chrome-'));
const browserLog = fs.openSync(path.join(profile, 'browser.log'), 'w');
const chrome = spawn(chromePath, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  // Only synthetic offline fixtures; Windows job restrictions can prevent the
  // browser's own sandbox from initializing in an automated test process.
  '--no-sandbox', '--disable-crash-reporter', '--disable-breakpad',
  '--disable-background-networking', '--disable-sync', '--disable-component-update', '--remote-debugging-port=0',
  `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', browserLog, browserLog] });
fs.closeSync(browserLog);
class CDP {
  constructor(url) {
    this.seq = 0; this.pending = new Map(); this.socket = new WebSocket(url);
    this.open = new Promise((resolve, reject) => { this.socket.onopen = resolve; this.socket.onerror = () => reject(new Error('Local Chrome connection failed')); });
    this.socket.onmessage = event => {
      const message = JSON.parse(event.data), pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id); clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(message.error.message)); else pending.resolve(message.result);
    };
  }
  async send(method, params = {}) {
    await this.open;
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`Local Chrome timed out: ${method}`)); }, 15000);
      this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }
  close() { this.socket.close(); for (const pending of this.pending.values()) clearTimeout(pending.timer); }
}
async function main() {
  let client;
  const checks = [];
  const stopChrome = () => {
    if (chrome.exitCode !== null || chrome.killed) return;
    if (process.platform === 'win32' && chrome.pid) {
      // Chrome owns subprocesses on Windows; terminate only the process tree
      // rooted at the instance this harness spawned.
      try { execFileSync('taskkill', ['/PID', String(chrome.pid), '/T', '/F'], { stdio: 'ignore' }); }
      catch { chrome.kill(); }
    } else chrome.kill();
  };
  try {
    let port;
    for (let i = 0; i < 300; i++) {
      const active = path.join(profile, 'DevToolsActivePort');
      try {
        const candidate = fs.readFileSync(active, 'utf8').split('\n')[0].trim();
        if (/^\d+$/.test(candidate)) { port = candidate; break; }
      } catch (error) {
        // Windows can observe the file while Chrome still holds its write lock.
        if (!['ENOENT', 'EBUSY', 'EACCES'].includes(error.code)) throw error;
      }
      if (chrome.exitCode !== null) throw new Error('Local Chrome exited before becoming ready');
      await pause(100);
    }
    if (!port) throw new Error('Local Chrome did not become ready');
    let pageTarget;
    for (let attempt = 0; attempt < 8 && !pageTarget; attempt++) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(1000) });
        if (response.ok) {
          const targets = await response.json();
          pageTarget = targets.find(target => target.type === 'page');
        }
      } catch { /* DevTools can publish its port file before its HTTP target list is ready. */ }
      if (!pageTarget) await pause(100);
      if (chrome.exitCode !== null) throw new Error('Local Chrome exited before exposing a page target');
    }
    if (!pageTarget) throw new Error('Local Chrome DevTools page target did not become ready');
    client = new CDP(pageTarget.webSocketDebuggerUrl);
    await client.send('Page.enable');
    await client.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    const pages = lessonOnly ? ['lesson-workspace'] : studioOnly ? ['studio'] : quizOnly ? ['quiz', 'quiz-result'] : ['home', 'detail', 'detail-flat', 'paid-preview', 'empty-home', 'lesson-workspace', 'studio', 'quiz', 'quiz-result'];
    const widths = studioKeyboardOnly ? [390] : [320, 390, 768, 1440];
    for (const name of pages) {
      const url = pathToFileURL(path.join(output, name + '.html')).href;
      for (const width of widths) {
        await client.send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
        await client.send('Page.navigate', { url });
        let ready = false;
        for (let i = 0; i < 60; i++) {
          const selector = name === 'lesson-workspace' ? '.lc-workspace' : name === 'studio' ? '.lc-studio-dashboard' : name.startsWith('quiz') ? (name === 'quiz' ? '.lc-question' : '.lc-quiz-feedback') : '.lc-academy';
          ready = await client.evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete' && !!document.querySelector(${JSON.stringify(selector)})`);
          if (ready) break;
          await pause(50);
        }
        assert.ok(ready, `${name} ready at ${width}`);
        const geometry = await client.evaluate(`({ width:innerWidth, scroll:document.documentElement.scrollWidth, cards:[...document.querySelectorAll('.lc-academy .lc-card')].every(e=>e.getBoundingClientRect().width>0), missingLabels:[...document.querySelectorAll('.lc-academy input:not([type=hidden]),.lc-academy select,.lc-academy textarea,.lc-question input')].filter(e=>!e.labels?.length).length })`);
        assert.ok(geometry.scroll <= geometry.width + 1, `${name} overflows at ${width}: ${JSON.stringify(geometry)}`);
        assert.ok(geometry.cards); assert.equal(geometry.missingLabels, 0);
        checks.push({ page: name, width, noOverflow: true, labeledInputs: true });
        if (width === 390 || width === 1440) {
          const screenshot = await client.send('Page.captureScreenshot', { format: 'png' });
          fs.writeFileSync(path.join(output, `${name}-${width}.png`), Buffer.from(screenshot.data, 'base64'));
        }
        if (name === 'lesson-workspace') {
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-workspace video[controls][playsinline]').length`), 1);
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace video track[kind="captions"][srclang="en-US"]') !== null`), true, 'caption track and language render');
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace [data-caption-toggle][aria-pressed="true"]') !== null`), true, 'caption control starts enabled');
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace details summary')?.textContent.trim()`), 'Read transcript', 'transcript disclosure renders');
          await client.evaluate(`document.querySelector('.lc-workspace [data-caption-toggle]').click()`);
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace [data-caption-toggle][aria-pressed="false"]') !== null`), true, 'caption toggle updates its accessible state');
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-workspace aside .lc-lesson-row').length`), 3);
          assert.deepEqual(await client.evaluate(`[...document.querySelectorAll('.lc-workspace aside .lc-module-title')].map(e=>e.textContent.trim())`), ['Foundations', 'Practice']);
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace .lc-lesson-row[aria-current="page"]') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace .lc-track[role="progressbar"]') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('.lc-workspace .lc-live-sessions')?.textContent.includes('Foundations live Q&A')`), true, 'lesson workspace exposes its authorized classroom session');
          if (width <= 767) assert.equal(await client.evaluate(`getComputedStyle(document.querySelector('.lc-workspace aside')).position`), 'static');
          await client.evaluate(`document.querySelector('.lc-workspace .lc-lesson-row[aria-current="page"]').focus()`);
          const focus = await client.evaluate(`({ visible:document.activeElement.matches(':focus-visible'), style:getComputedStyle(document.activeElement).outlineStyle })`);
          assert.ok(focus.visible); assert.notEqual(focus.style, 'none');
          checks.push({ page: name, width, player: true, curriculum: true, responsiveSidebar: true });
        }
        if (name === 'studio') {
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-studio-dashboard .lc-studio-check').length`), 3);
          assert.equal(await client.evaluate(`document.querySelector('.lc-studio-dashboard .lc-studio-quiz') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('.lc-studio-dashboard .lc-notice') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('#new-module-title')?.required`), true, 'web Studio offers an optional section title field');
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-studio-dashboard input[type=number][min="1"]').length`), 2, 'web Studio exposes section ordering controls');
          if (studioKeyboardOnly) {
            await client.evaluate(`document.body.focus()`);
            await client.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
            await client.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
            const keyboard = await client.evaluate(`({ href:document.activeElement.getAttribute('href'), visible:document.activeElement.matches(':focus-visible'), outline:getComputedStyle(document.activeElement).outlineStyle })`);
            assert.equal(keyboard.href, '/learning/classrooms/', `Studio first Tab target: ${JSON.stringify(keyboard)}`);
            assert.ok(keyboard.visible); assert.notEqual(keyboard.outline, 'none');
            await client.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
            await client.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
            assert.equal(await client.evaluate(`document.activeElement.textContent.trim()`), 'Discover');
            checks.push({ page: name, width, keyboardTabOrder: true, visibleFocus: true });
          } else checks.push({ page: name, width, checklist: true, moderationFeedback: true });
        }
        if (name === 'quiz') {
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-question legend').length`), 1);
          assert.equal(await client.evaluate(`document.querySelectorAll('.lc-question input[type=radio]').length`), 4);
          await client.evaluate(`document.querySelector('.lc-question input[type=radio]').focus()`);
          const focus = await client.evaluate(`({ visible:document.activeElement.matches(':focus-visible'), outline:getComputedStyle(document.activeElement).outlineStyle })`);
          assert.ok(focus.visible); assert.notEqual(focus.outline, 'none');
          await client.send('Input.dispatchKeyEvent', { type: 'keyDown', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 });
          await client.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 });
          assert.equal(await client.evaluate(`document.querySelector('.lc-question input[type=radio]').checked`), true);
        }
        if (name === 'quiz-result') {
          assert.equal(await client.evaluate(`document.querySelector('.lc-quiz-feedback[aria-labelledby="quiz-feedback-title"]') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('.lc-quiz-feedback-item.is-incorrect') !== null`), true);
          assert.equal(await client.evaluate(`document.querySelector('.lc-quiz-feedback-item').querySelector('h3') !== null`), true);
        }
      }
      if (name === 'home') {
        const headings = await client.evaluate(`[...document.querySelectorAll('.lc-academy h2')].map(e=>e.textContent)`);
        for (const title of ['Continue Learning', 'Explore Courses', 'Live sessions']) assert.ok(headings.includes(title));
        await client.evaluate(`document.querySelector('#learning-search').focus()`);
        assert.equal(await client.evaluate('document.activeElement.id'), 'learning-search');
        await client.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
        await client.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
        assert.equal(await client.evaluate('document.activeElement.id'), 'learning-category');
        const focus = await client.evaluate(`({ visible:document.activeElement.matches(':focus-visible'), style:getComputedStyle(document.activeElement).outlineStyle })`);
        assert.ok(focus.visible, JSON.stringify(focus)); assert.notEqual(focus.style, 'none');
        await client.evaluate(`document.querySelector('a[href="#explore-courses"]').click()`);
        assert.equal(await client.evaluate('location.hash'), '#explore-courses');
        assert.equal(await client.evaluate(`getComputedStyle(document.querySelector('#explore-courses')).scrollMarginTop`), '140px');
      }
      if (name === 'detail' || name === 'detail-flat' || name === 'paid-preview') {
        assert.equal(await client.evaluate(`[...document.querySelectorAll('.lc-section-nav a')].every(e=>!!document.querySelector(e.getAttribute('href')))`), true);
        assert.equal(await client.evaluate(`document.querySelectorAll('.lc-lesson-row[href]').length`), ['detail', 'detail-flat'].includes(name) ? 3 : 0);
        if (name === 'detail') assert.deepEqual(await client.evaluate(`[...document.querySelectorAll('#curriculum .lc-module-title')].map(e=>e.textContent.trim())`), ['Foundations', 'Practice']);
        if (name === 'detail') assert.equal(await client.evaluate(`document.querySelector('.lc-live-sessions')?.textContent.includes('Foundations live Q&A')`), true, 'course detail shows the linked lesson session');
        if (name === 'detail') assert.equal(await client.evaluate(`document.querySelector('.lc-live-sessions a[href*="/classroom/"]') !== null`), true, 'course session opens the existing classroom route');
        if (name === 'detail-flat') assert.equal(await client.evaluate(`document.querySelectorAll('#curriculum .lc-module-title').length`), 0);
        if (name === 'paid-preview') assert.equal(await client.evaluate(`document.querySelector('#enroll button').disabled`), true);
      }
    }
    fs.writeFileSync(path.join(output, 'browser-report.json'), JSON.stringify({ passed: true, checks, keyboard: 'search focus outline and Tab to category passed', scope: 'Real Learning templates and stylesheet in isolated offline shell; no production or native-device verification' }, null, 2));
    const layoutCount = checks.filter(check => check.noOverflow).length;
    console.log(`PASS: ${layoutCount} responsive layouts, form labels, keyboard focus/order, section navigation and enrollment states.`);
  } finally {
    client?.close(); stopChrome();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
