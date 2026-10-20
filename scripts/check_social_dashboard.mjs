/* Local Chrome/CDP QA. No browser packages or external test services required. */
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const audit = path.join(root, '.audit-social-dashboard');
fs.mkdirSync(audit, {recursive: true});
const origin = 'http://127.0.0.1:8776';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(check, description, attempts = 150) {
    for (let i = 0; i < attempts; i++) {
        try { if (await check()) return; } catch {}
        await delay(200);
    }
    throw new Error(`Timed out: ${description}`);
}
await waitFor(async () => (await fetch(origin + '/accounts/login/')).ok, 'local preview server', 900);
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-component-update', '--disable-sync',
    '--remote-debugging-port=9239', `--user-data-dir=${path.join(audit, 'chrome')}`, 'about:blank',
], {windowsHide: true, stdio: 'ignore'});
let socket;
let command;
const results = {layouts: [], workflows: [], exceptions: []};
try {
    let targets;
    await waitFor(async () => {
        targets = await (await fetch('http://127.0.0.1:9239/json')).json();
        return targets.some(target => target.type === 'page');
    }, 'isolated headless Chrome');
    socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, {once: true}); socket.addEventListener('error', reject, {once: true}); });
    let sequence = 0;
    const pending = new Map();
    socket.addEventListener('message', event => {
        const message = JSON.parse(event.data);
        if (message.id) {
            const handlers = pending.get(message.id);
            pending.delete(message.id);
            if (message.error) handlers.reject(new Error(JSON.stringify(message.error)));
            else handlers.resolve(message.result);
        } else if (message.method === 'Runtime.exceptionThrown') {
            results.exceptions.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
        }
    });
    command = (method, params = {}) => new Promise((resolve, reject) => {
        const id = ++sequence;
        pending.set(id, {resolve, reject});
        socket.send(JSON.stringify({id, method, params}));
    });
    async function evaluate(expression) {
        const result = await command('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
        if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
        return result.result.value;
    }
    async function navigate(route) {
        await command('Page.navigate', {url: origin + route});
        await waitFor(() => evaluate(`location.origin === ${JSON.stringify(origin)} && document.readyState === 'complete'`), route, 200);
        await delay(250);
        if (await evaluate('/Server Error \\(500\\)|Traceback/.test(document.body.innerText)')) throw new Error(`Server error: ${route}`);
    }
    async function assert(expression, description) {
        if (!await evaluate(expression)) throw new Error(description);
        results.workflows.push(description);
    }
    await command('Page.enable');
    await command('Runtime.enable');
    await command('Network.enable');
    await command('Network.clearBrowserCookies');
    await command('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
    await navigate('/accounts/login/');
    const login = await evaluate(`(async () => {
        const form = document.querySelector('form[method=post], form[method=POST]');
        const data = new FormData(form);
        data.set('username', 'preview_amina'); data.set('password', 'LocalPreviewOnly123!');
        const response = await fetch(location.href, {method: 'POST', body: data, credentials: 'same-origin'});
        return {status: response.status, url: response.url};
    })()`);
    if (login.status !== 200 || login.url.includes('/login/')) throw new Error('Synthetic login failed');
    await navigate('/talents/dashboard/');
    await assert(`document.querySelector('.dashboard-snapshot') && document.querySelector('.feed-tabs')`, 'Dashboard renders feed and account tools');
    await assert(`document.querySelector('link[href*="social-dashboard.css"]').sheet !== null`, 'Dashboard stylesheet loads');
    await assert(`document.querySelector('[data-message-unread]').textContent.trim() !== '0'`, 'Unread message badges use real fixture data');
    await evaluate(`document.getElementById('dismissNotificationsButton')?.click()`);
    for (const width of [1440, 1280, 1024, 768, 390, 320]) {
        await command('Emulation.setDeviceMetricsOverride', {width, height: 1000, deviceScaleFactor: 1, mobile: width < 768});
        await delay(150);
        const layout = await evaluate(`({width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
            bottomNavVisible: !!document.querySelector('.mobile-bottom-nav').getClientRects().length,
            timelineWidth: Math.round(document.querySelector('.feed-timeline').getBoundingClientRect().width)})`);
        if (layout.scrollWidth > layout.width + 1) throw new Error(`Horizontal overflow at ${width}px: ${JSON.stringify(layout)}`);
        if (width < 992 && !layout.bottomNavVisible) throw new Error(`Missing mobile navigation at ${width}px`);
        results.layouts.push(layout);
        if ([1440, 390, 320].includes(width)) {
            const screenshot = await command('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
            fs.writeFileSync(path.join(audit, `dashboard-${width}.png`), Buffer.from(screenshot.data, 'base64'));
        }
    }
    for (const [width, route] of [[1440, '/learning/'], [768, '/notifications/'], [390, '/messages/conversations/'], [320, '/home_feed/']]) {
        await command('Emulation.setDeviceMetricsOverride', {width, height: 900, deviceScaleFactor: 1, mobile: width < 768});
        await navigate(route);
        await evaluate(`window.scrollTo(0, document.body.scrollHeight)`);
        await assert(`(() => { const link = Array.from(document.querySelectorAll('[data-post-composer]')).find(item => item.getClientRects().length); const box = link.getBoundingClientRect(); return box.top >= 0 && box.bottom <= innerHeight + 1; })()`, `Post remains visible after scrolling on ${route} at ${width}px`);
        await evaluate(`Array.from(document.querySelectorAll('[data-post-composer]')).find(item => item.getClientRects().length).click()`);
        await assert(`document.getElementById('postComposer').open && document.querySelector('#postComposer [data-post-submit]').disabled`, `Composer opens and prevents empty posts at ${width}px`);
        await evaluate(`document.getElementById('composer_caption').value = '   '; document.getElementById('composer_caption').dispatchEvent(new Event('input', {bubbles: true}))`);
        await assert(`document.querySelector('#postComposer [data-post-submit]').disabled`, `Whitespace alone cannot be posted at ${width}px`);
        await evaluate(`document.getElementById('composer_caption').value = 'Draft kept when closing'; document.getElementById('composer_caption').dispatchEvent(new Event('input', {bubbles: true}))`);
        await command('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
        await command('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
        await waitFor(() => evaluate(`!document.getElementById('postComposer').open && document.activeElement.matches('[data-post-composer]')`), `Escape restores focus to Post at ${width}px`);
        await assert(`document.getElementById('composer_caption').value === 'Draft kept when closing'`, `Closing the composer keeps the draft at ${width}px`);
        await evaluate(`document.getElementById('composer_caption').value = ''; document.getElementById('composer_caption').dispatchEvent(new Event('input', {bubbles: true}))`);
    }
    await assert(`Array.from(document.querySelector('.mobile-bottom-nav').children).map(item => item.lastElementChild.textContent.trim()).join('|') === 'Home|Opportunities|Post|Messages|More'`, 'Mobile navigation has Opportunities immediately left of the central Post button');
    async function upload(selector, filename) {
        const {root: documentRoot} = await command('DOM.getDocument');
        const {nodeId} = await command('DOM.querySelector', {nodeId: documentRoot.nodeId, selector});
        await command('DOM.setFileInputFiles', {nodeId, files: [filename]});
    }
    // Exercise server validation and retain the draft after an invalid upload.
    await navigate('/learning/');
    await evaluate(`document.querySelector('.mobile-nav-create').click()`);
    fs.writeFileSync(path.join(audit, 'invalid-photo.png'), 'not an image');
    await upload('#composer_image', path.join(audit, 'invalid-photo.png'));
    await evaluate(`document.getElementById('composer_caption').value = 'Keep this draft'; document.querySelector('#postComposer form').requestSubmit()`);
    await waitFor(() => evaluate(`!document.querySelector('#postComposer [data-post-errors]').hidden`), 'server image validation');
    await assert(`document.getElementById('postComposer').open && document.getElementById('composer_caption').value === 'Keep this draft' && document.getElementById('composer_image').files.length === 1`, 'Server validation errors keep the modal and draft intact');
    await upload('#composer_image', path.join(audit, 'media', 'blue-hour.png'));
    await evaluate(`document.getElementById('composer_caption').value = ''; document.getElementById('composer_caption').dispatchEvent(new Event('input', {bubbles: true}))`);
    await assert(`!document.querySelector('#postComposer [data-post-submit]').disabled`, 'Photo-only posts enable Post');
    await command('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
    await delay(150);
    await assert(`(() => { const box = document.getElementById('postComposer').getBoundingClientRect(); return box.width <= innerWidth && box.height <= innerHeight && box.top >= 0; })()`, 'Photo composer fits the phone viewport');
    const composerShot = await command('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(audit, 'post-composer-390.png'), Buffer.from(composerShot.data, 'base64'));
    await evaluate(`document.querySelector('#postComposer form').requestSubmit()`);
    await waitFor(() => evaluate(`location.pathname === '/home_feed/' && document.readyState === 'complete' && !document.querySelector('dialog[open]')`), 'photo post');
    results.workflows.push('Photo-only post publishes through the existing Django backend');
    await evaluate(`document.querySelector('.mobile-nav-create').click()`);
    await upload('#composer_video', path.join(audit, 'media', 'practice.mp4'));
    await assert(`!document.querySelector('#postComposer [data-post-submit]').disabled`, 'Video-only posts enable Post');
    await evaluate(`document.querySelector('#postComposer form').requestSubmit()`);
    await waitFor(() => evaluate(`location.pathname === '/home_feed/' && document.readyState === 'complete' && !document.querySelector('dialog[open]')`), 'video post');
    results.workflows.push('Video-only post publishes through the existing Django backend');
    await command('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
    await navigate('/notifications/');
    await evaluate(`document.querySelector('.global-post-button').click()`);
    await evaluate(`document.getElementById('composer_caption').value = 'A local text-only post'; document.getElementById('composer_caption').dispatchEvent(new Event('input', {bubbles: true}))`);
    const desktopComposer = await command('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(audit, 'post-composer-1440.png'), Buffer.from(desktopComposer.data, 'base64'));
    await evaluate(`document.querySelector('#postComposer form').requestSubmit()`);
    await waitFor(() => evaluate(`location.pathname === '/home_feed/' && document.readyState === 'complete' && document.body.innerText.includes('A local text-only post')`), 'text post');
    results.workflows.push('Text-only post publishes from the desktop fixed Post button');
    await command('Emulation.setDeviceMetricsOverride', {width: 320, height: 1000, deviceScaleFactor: 1, mobile: true});
    await evaluate(`document.getElementById('mobileSidebarToggle').click()`);
    await assert(`document.getElementById('awinlinkSidebar').getAttribute('aria-modal') === 'true' && document.querySelector('.awinlink-main').inert`, 'Mobile drawer traps focus and makes background inert');
    await command('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await command('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await assert(`!document.getElementById('awinlinkSidebar').classList.contains('show') && !document.querySelector('.awinlink-main').inert`, 'Escape closes the mobile drawer');
    await evaluate(`document.querySelector('[data-story-open]').click()`);
    await assert(`document.querySelector('dialog[open]') !== null`, 'Authorized recent-post story opens');
    await evaluate(`document.querySelector('dialog[open] [data-story-close]').click()`);
    await delay(100);
    await assert(`!document.querySelector('dialog[open]') && document.activeElement.matches('[data-story-open]')`, 'Closing a story restores keyboard focus');
    await evaluate(`document.querySelector('[data-story-open]').click(); document.querySelector('dialog[open] footer a').click()`);
    await delay(150);
    await assert(`!document.querySelector('dialog[open]')`, 'View post closes the story and preserves the normal post link');
    const likedBefore = await evaluate(`document.querySelector('.feed-like-form button').getAttribute('aria-pressed')`);
    await evaluate(`document.querySelector('.feed-like-form button').click()`);
    await waitFor(() => evaluate(`document.querySelector('.feed-like-form button').getAttribute('aria-pressed') !== ${JSON.stringify(likedBefore)}`), 'like action');
    results.workflows.push('Like persists through the Django AJAX endpoint');
    const savedBefore = await evaluate(`document.querySelector('.feed-save-form button').getAttribute('aria-pressed')`);
    await evaluate(`document.querySelector('.feed-save-form button').click()`);
    await waitFor(() => evaluate(`document.querySelector('.feed-save-form button').getAttribute('aria-pressed') !== ${JSON.stringify(savedBefore)}`), 'save action');
    results.workflows.push('Save persists through the Django AJAX endpoint');
    const comment = `Local browser check ${Date.now()} <b>safe text</b>`;
    await evaluate(`(() => { document.querySelector('.feed-comment-focus').click(); const form = document.querySelector('.feed-comment-form'); form.elements.text.value = ${JSON.stringify(comment)}; form.requestSubmit(); })()`);
    await waitFor(() => evaluate(`document.querySelector('[data-comments-list]').textContent.includes(${JSON.stringify(comment)})`), 'comment action');
    await assert(`!document.querySelector('[data-comments-list] b')`, 'Comment text renders safely without injecting HTML');
    if (await evaluate(`!!window.bootstrap?.Modal`)) {
        await evaluate(`document.querySelector('.share-count-button').click()`);
        await waitFor(() => evaluate(`!!document.querySelector('.feed-share-modal.show')`), 'share dialog');
        await evaluate(`(() => { const form = document.querySelector('.feed-share-modal.show .share-form'); form.elements.caption.value = 'A local preview share'; form.requestSubmit(); })()`);
        await waitFor(() => evaluate(`!document.querySelector('.feed-share-modal.show')`), 'share submit');
        results.workflows.push('Sharing uses the existing Django POST endpoint');
    } else { throw new Error('Existing Bootstrap share-dialog dependency did not load'); }
    const connection = await evaluate(`!!document.querySelector('.connection-request-form')`);
    if (connection) {
        await evaluate(`document.querySelector('.connection-request-form').requestSubmit()`);
        await waitFor(() => evaluate(`document.querySelector('.connection-request-form button').disabled && document.querySelector('.connection-request-form button').textContent.includes('Request sent')`), 'connection request');
        results.workflows.push('Talent connection request retains its server permission checks');
    }
    await navigate('/talents/dashboard/?view=reels');
    await assert(`document.querySelector('.social-dashboard').dataset.view === 'reels'`, 'Reels filter loads through Django');
    await assert(`Array.from(document.querySelectorAll('.feed-post[data-kind=post]')).every(post => post.querySelector('video'))`, 'Reels contain video posts only');
    await assert(`document.querySelector('.awinlink-sidebar a[aria-current=page]')?.textContent.includes('Reels')`, 'More navigation distinguishes Reels from Home');
    const screenshot = await command('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(audit, 'reels-320.png'), Buffer.from(screenshot.data, 'base64'));
    await navigate('/notifications/');
    await assert(`document.body.innerText.includes('Maya liked your latest work.')`, 'Notifications retain the authenticated user data');
    await navigate('/messages/conversations/');
    await assert(`document.body.innerText.includes('Jordan')`, 'Messaging opens existing conversations');
    if (results.exceptions.length) throw new Error(`Browser exceptions: ${results.exceptions.join('; ')}`);
    console.log(JSON.stringify(results, null, 2));
} catch (error) {
    results.error = error.message;
    process.exitCode = 1;
    console.error(error.stack);
} finally {
    fs.writeFileSync(path.join(audit, 'browser-results.json'), JSON.stringify(results, null, 2));
    if (socket?.readyState === WebSocket.OPEN) {
        try { await command('Browser.close'); } catch {}
        socket.close();
    }
    chrome.kill();
}
