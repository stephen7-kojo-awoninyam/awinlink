/* Real browser codecs and recording; no microphone, user files or external service. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const chrome = process.env.MEDIA_TEST_CHROME;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

test('real browser records and plays voice/video at desktop and mobile widths', { skip: !chrome, timeout: 180000 }, async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-media-browser-'));
  const fixturePath = path.join(directory, 'fixture.mp4');
  const python = path.join(__dirname, '../../.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const binaries = path.join(__dirname, '../../.venv/Lib/site-packages/imageio_ffmpeg/binaries');
  const ffmpeg = process.env.MEDIA_TEST_FFMPEG || (process.platform === 'win32' && fs.existsSync(binaries) ? fs.readdirSync(binaries).find(name => /^ffmpeg.*\.exe$/.test(name)) : null);
  const args = ['-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=blue:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-shortest',fixturePath];
  const generated = ffmpeg
    ? spawnSync(path.isAbsolute(ffmpeg) ? ffmpeg : path.join(binaries, ffmpeg), args, { windowsHide: true, timeout: 60000, encoding: 'utf8' })
    : spawnSync(python, ['-c', 'import subprocess,sys; from imageio_ffmpeg import get_ffmpeg_exe; subprocess.run([get_ffmpeg_exe(),*sys.argv[1:]],check=True)', ...args], { windowsHide: true, timeout: 60000, encoding: 'utf8' });
  assert.equal(generated.status, 0, generated.error?.message || generated.stderr);
  const videoFixture = fs.readFileSync(fixturePath);
  const script = fs.readFileSync(path.join(__dirname, '../../static/js/recording-format.js'), 'utf8');
  const server = http.createServer((request, response) => {
    if (request.url === '/fixture.mp4') {
      response.setHeader('Content-Type', 'video/mp4');
      response.end(videoFixture);
      return;
    }
    response.setHeader('Content-Type', 'text/html');
    response.end(`<html><meta name="viewport" content="width=device-width"><body><script>${script}</script></body></html>`);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const child = spawn(chrome, ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-component-update', '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', `--user-data-dir=${directory}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let launchError = '';
  child.stderr.on('data', data => { launchError = (launchError + data).slice(-1500); });
  child.on('error', error => { launchError = error.message; });
  let socket;
  try {
    const portFile = path.join(directory, 'DevToolsActivePort');
    for (let count = 0; !fs.existsSync(portFile) && count < 300 && child.exitCode === null; count++) await pause(100);
    if (!fs.existsSync(portFile)) throw new Error(`Chrome did not start (exit ${child.exitCode}): ${launchError}`);
    const port = fs.readFileSync(portFile, 'utf8').split('\n')[0];
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let sequence = 0;
    const pending = new Map();
    socket.onmessage = event => {
      const data = JSON.parse(event.data);
      if (pending.has(data.id)) {
        const { resolve, reject, timer } = pending.get(data.id); pending.delete(data.id); clearTimeout(timer);
        data.error ? reject(new Error(data.error.message)) : resolve(data.result);
      }
    };
    function send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = ++sequence;
        const timer = setTimeout(() => reject(new Error(`Timeout: ${method}`)), 20000);
        pending.set(id, { resolve, reject, timer });
        socket.send(JSON.stringify({ id, method, params }));
      });
    }
    async function evaluate(expression) {
      const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
      return result.result.value;
    }
    await send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
    for (let count = 0; !await evaluate('!!window.recordingFormat') && count < 50; count++) await pause(100);
    for (const width of [1440, 390]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height: 844, deviceScaleFactor: 1, mobile: width === 390 });
      const result = await evaluate(`(async () => {
        const context = new AudioContext(); await context.resume();
        const oscillator = context.createOscillator();
        const destination = context.createMediaStreamDestination();
        oscillator.connect(destination); oscillator.start();
        async function capture(stream, type) {
          const recorder = type ? new MediaRecorder(stream, {mimeType:type}) : new MediaRecorder(stream);
          const chunks=[]; recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
          const stopped = new Promise(resolve=>recorder.onstop=resolve);
          recorder.start(); await new Promise(resolve=>setTimeout(resolve,700)); recorder.stop(); await stopped;
          return new Blob(chunks,{type:recorder.mimeType || chunks[0].type});
        }
        async function play(blob, tag) {
          const element = document.createElement(tag); element.controls=true; element.muted=true; element.style.width='100%';
          if(tag==='video')element.playsInline=true;
          const url=URL.createObjectURL(blob); element.src=url; document.body.append(element);
          try {
            await new Promise((resolve,reject)=>{element.onloadeddata=resolve;element.onerror=()=>reject(Error('decode '+tag+' '+blob.type+' '+blob.size+' bytes: '+element.error?.message));element.load();});
            await element.play(); await new Promise(resolve=>setTimeout(resolve,200));
            if(element.currentTime<=0)throw Error('Playback did not advance');
            element.pause(); element.currentTime=0;
            return {type:blob.type,bytes:blob.size,controls:element.controls};
          } finally {element.remove();URL.revokeObjectURL(url);}
        }
        try {
          const audio=await capture(destination.stream,recordingFormat.select(MediaRecorder));
          const video=await (await fetch('/fixture.mp4')).blob();
          return {audio:await play(audio,'audio'),video:await play(video,'video')};
        } finally {destination.stream.getTracks().forEach(track=>track.stop());oscillator.stop();await context.close();}
      })()`);
      assert.ok(result.audio.bytes > 0); assert.ok(result.video.bytes > 0);
      assert.equal(result.audio.controls, true); assert.equal(result.video.controls, true);
      console.log(`Browser ${width}px: ${JSON.stringify(result)}`);
    }
    await send('Browser.close');
  } finally {
    socket?.close(); child.kill();
    await new Promise(resolve => server.close(resolve));
    if (path.dirname(path.resolve(directory)) !== path.resolve(os.tmpdir()) || !path.basename(directory).startsWith('awinlink-media-browser-')) throw new Error('Unexpected browser temporary directory');
    for (let count = 0; count < 30; count++) {
      try { fs.rmSync(directory, { recursive: true, force: true }); break; }
      catch { await pause(100); }
    }
  }
});
