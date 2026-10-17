/* Headless Chrome UI smoke test with synthetic media and authenticated API/socket fixtures. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, writeFileSync, mkdtempSync, rmSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const { resolve, join, dirname, basename } = require('node:path');
const { pathToFileURL } = require('node:url');
const chrome = process.env.CLASSROOM_TEST_CHROME;
test('browser controls, whiteboard, plaintext chat, media cleanup and mobile viewport', { skip: !chrome }, () => {
  const root = resolve(__dirname, '../..');
  const temporary = mkdtempSync(join(root, '.classroom-browser-test-'));
  try {
    const template = readFileSync(join(root, 'learning/templates/learning/classroom.html'), 'utf8');
    const main = template.slice(template.indexOf('<main'), template.indexOf('</main>') + 7)
      .replace(/\{%[\s\S]*?%\}/g, '').replace(/\{\{ session.id \}\}/g, '7').replace(/\{\{[\s\S]*?\}\}/g, 'Drawing class');
    const css = readFileSync(join(root, 'static/css/classroom.css'), 'utf8');
    const client = readFileSync(join(root, 'static/js/classroom-client.js'), 'utf8');
    const browser = readFileSync(join(root, 'static/js/classroom-browser.js'), 'utf8');
    const fixtures = `
      window.requests=[]; window.captures=[]; window.testSockets=[]; window.injected=false;
      class Track {constructor(kind){this.kind=kind;this.enabled=true;} stop(){this.stopped=true;}}
      class Stream {constructor(tracks=[]){this.tracks=tracks;}getTracks(){return this.tracks;}getAudioTracks(){return this.tracks.filter(t=>t.kind==='audio');}getVideoTracks(){return this.tracks.filter(t=>t.kind==='video');}addTrack(track){this.tracks.push(track);}}
      window.MediaStream=Stream;
      Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async c=>{const s=new Stream([...(c.audio?[new Track('audio')]:[]),...(c.video?[new Track('video')]:[])]);captures.push(s);return s;},getDisplayMedia:async()=>{const s=new Stream([new Track('video')]);captures.push(s);return s;}}});
      Object.defineProperty(HTMLMediaElement.prototype,'srcObject',{get(){return this._stream;},set(v){this._stream=v;},configurable:true});
      HTMLMediaElement.prototype.play=async()=>{};
      window.confirm=()=>true;
      const board={session_id:7,revision:0,objects:{},editors:[],can_edit:true,can_manage:true};
      const session={id:7,status:'LIVE',my_participant:{id:10,role:'HOST',admission_state:'ADMITTED'},capabilities:{end:true,participants:true,admit:true,remove:true,start:false,cancel:false}};
      window.fetch=async(path,options={})=>{const data=options.body?JSON.parse(options.body):null;requests.push({path,options,data});let result=session;
        if(path.includes('ice-servers'))result={ice_servers:[{urls:'stun:example.invalid'}]};
        else if(path.includes('participants/'))result={results:[{id:20,user:20,role:'LEARNER',admission_state:'WAITING',display_name:'Learner <img src=x>'}]};
        else if(path.endsWith('whiteboard/')){if(data){board.revision++;if(data.action==='add')board.objects[data.payload.id]=data.payload;if(data.action==='clear')board.objects={};}result=board;}
        else if(path.endsWith('chat/'))result={id:1,client_id:data.client_id,sender_name:'Learner',text:data.text};
        return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(result))};};
      class Socket {constructor(url){this.url=url;this.readyState=1;testSockets.push(this);setTimeout(()=>{this.onmessage?.({data:JSON.stringify(url.includes('whiteboard')?{type:'snapshot',...board}:{type:'connection',session_id:7,participant_id:10,peers:[]})});},40);}send(text){const data=JSON.parse(text);if(data.type==='chat_history')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'chat_history',messages:[]})}),0);}close(){this.readyState=3;this.onclose?.({code:1000});}}
      window.WebSocket=Socket;
      window.RTCPeerConnection=class {};
    `;
    const assertions = `
      const pause=ms=>new Promise(r=>setTimeout(r,ms));
      function check(condition,label){if(!condition)throw new Error(label);}
      (async()=>{await pause(100);
        check(document.getElementById('vc-join').disabled===false,'admitted learner join button');
        check(document.querySelector('[data-action=start]').hidden,'server forbids start');
        check(document.querySelector('#vc-roster img')===null,'participant names rendered as text');
        document.getElementById('vc-join').click();await pause(150);
        check(document.getElementById('vc-status').textContent.includes('Connected'),'socket connected');
        check(document.getElementById('vc-message').disabled===false,'chat enabled');
        const malicious='<img src=x onerror="window.injected=true">';
        document.getElementById('vc-message').value=malicious;document.getElementById('vc-chat-form').dispatchEvent(new Event('submit',{cancelable:true}));await pause(60);
        check(document.getElementById('vc-chat').textContent.includes(malicious),'plain chat content');check(!document.querySelector('#vc-chat img')&&!window.injected,'chat cannot execute HTML');
        const canvas=document.getElementById('vc-board');canvas.setPointerCapture=()=>{};const rect=canvas.getBoundingClientRect();
        document.getElementById('vc-tool').value='text';document.getElementById('vc-board-text').value='Shared note';canvas.dispatchEvent(new PointerEvent('pointerdown',{clientX:rect.left+rect.width*.2,clientY:rect.top+rect.height*.2,pointerId:1}));await pause(60);
        check(requests.some(r=>r.data?.action==='add'&&r.data.payload.text==='Shared note'),'whiteboard sends command');
        check(document.getElementById('vc-board-content').textContent.includes('Shared note'),'accessible board text');
        document.getElementById('vc-share').click();await pause(40);check(document.getElementById('vc-share').textContent==='Stop sharing','screen sharing starts');document.getElementById('vc-share').click();await pause(40);
        const actorButtons=[...document.querySelectorAll('#vc-roster button')];actorButtons.find(b=>b.textContent==='Admit').click();await pause(30);check(requests.some(r=>r.path.endsWith('/participants/20/admit/')),'host admit API');
        check(document.documentElement.scrollWidth<=window.innerWidth+1,'mobile viewport has no horizontal overflow');
        document.getElementById('vc-leave').click();await pause(40);check(captures.every(s=>s.getTracks().every(t=>t.stopped)),'leave stops all capture');check(document.querySelectorAll('#vc-chat p').length===0,'leave clears chat');
        document.getElementById('result').textContent='CLASSROOM_BROWSER_OK';
      })().catch(error=>{document.getElementById('result').textContent='CLASSROOM_BROWSER_FAILED: '+error.message;});
    `;
    const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;padding:12px;box-sizing:border-box}*{box-sizing:border-box}${css}</style></head><body>${main}<pre id="result">RUNNING</pre><script>${fixtures}</script><script>${client}</script><script>${browser}</script><script>${assertions}</script></body></html>`;
    const file = join(temporary, 'test.html'); writeFileSync(file, html);
    const output = spawnSync(chrome, ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-component-update', '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check',
      `--user-data-dir=${join(temporary, 'profile')}`, '--window-size=390,844', '--virtual-time-budget=3000', '--dump-dom', pathToFileURL(file).href],
      { timeout: 90000, encoding: 'utf8', windowsHide: true, maxBuffer: 4 * 1024 * 1024 });
    assert.equal(output.status, 0, output.error?.message || output.stderr);
    const result = output.stdout.match(/<pre id="result">([^<]*)<\/pre>/)?.[1];
    assert.equal(result, 'CLASSROOM_BROWSER_OK');
  } finally {
    // Only the exact test-owned directory created above is removed.
    assert.equal(dirname(temporary), root);
    assert.match(basename(temporary), /^\.classroom-browser-test-/);
    rmSync(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
});
