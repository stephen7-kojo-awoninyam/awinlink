/* Exercise Phase 1 DOM controls with isolated browser fixtures; no real accounts. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, writeFileSync, mkdtempSync, rmSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const { resolve, join, dirname } = require('node:path');
const { pathToFileURL } = require('node:url');
const chrome = process.env.CLASSROOM_TEST_CHROME;
test('Phase 1 browser controls send authorized API payloads and escape user content', { skip: !chrome }, () => {
  const root = resolve(__dirname, '../..');
  const temporary = mkdtempSync(join(root, '.classroom-browser-test-phase1-'));
  try {
    const script = readFileSync(join(root, 'static/js/classroom-management.js'), 'utf8').replaceAll('location.origin', "'https://fixture.invalid'");
    const css = readFileSync(join(root, 'static/css/classroom.css'), 'utf8');
    const fixture = `
      window.calls=[]; window.errors=[]; window.onerror=message=>errors.push(message); window.confirm=()=>true;
      window.fetch=async(url,options={})=>{
        const parsed=new URL(url), path=parsed.pathname, data=options.body?JSON.parse(options.body):undefined;
        calls.push({path,data,options});
        if(options.method==='POST')return {ok:false,status:400,json:async()=>({error:{detail:'Fixture mutation captured'}})};
        let results=[];
        if(path.endsWith('/courses/me/'))return {ok:true,status:200,json:async()=>[{id:1,title:'Course <img src=x>'}]};
        if(path.endsWith('/lessons/'))return {ok:true,status:200,json:async()=>[{id:2,title:'Lesson'}]};
        if(path.endsWith('/classroom-invitations/'))results=[{id:3,classroom_title:'Invitation <img src=x>',status:'PENDING',is_expired:false,message:'Hello <img src=x>'}];
        if(path.endsWith('/invitations/'))results=[{id:4,recipient:42,recipient_username:'learner.name',status:'PENDING',is_expired:false}];
        if(path.endsWith('/users/'))results=parsed.searchParams.get('purpose')==='invite'?[{id:42,username:'learner.name',display_name:'Learner <img src=x>'}]:[{id:43,username:'cohost.name',display_name:'Cohost <img src=x>'}];
        if(path.endsWith('/staff/'))results=[{id:5,user:43,username:'cohost.name',display_name:'Cohost <img src=x>',role:'COHOST'}];
        return {ok:true,status:200,json:async()=>({results,next:null})};
      };
    `;
    const assertions = `
      const pause=()=>new Promise(r=>setTimeout(r,40));
      function check(ok,label){if(!ok)throw new Error(label);}
      async function click(label, scope=document){const b=[...scope.querySelectorAll('button')].find(b=>b.textContent===label);check(b,'Missing '+label);b.click();await pause();}
      function fill(form,label,value){const wrapper=[...form.querySelectorAll('label')].find(l=>l.textContent.trim()===label);check(wrapper,'Missing field '+label);const input=wrapper.querySelector('input');input.value=value;input.dispatchEvent(new Event('input'));return input;}
      async function submit(summary,values){const details=[...document.querySelectorAll('details')].find(d=>d.querySelector('summary').textContent===summary);check(details,'Missing form '+summary);const f=details.querySelector('form');for(const [label,value]of Object.entries(values))fill(f,label,value);f.dispatchEvent(new Event('submit',{cancelable:true}));await pause();}
      (async()=>{await pause();await pause();
        check(window.AwinClassroomManagement, 'Script errors: '+errors.join(';'));const room=document.getElementById('room');window.AwinClassroomManagement.room(room,{id:9,course:1,capabilities:{manage:true,staff:true}});
        const learner=document.getElementById('learner');window.AwinClassroomManagement.room(learner,{id:10,course:1,capabilities:{manage:false,staff:false}});check(!learner.querySelector('button'),'learner management hidden');
        await submit('Create classroom',{'Classroom title':'New room','Seats':'12'});
        check(calls.some(c=>c.path==='/api/learning/classrooms/'&&c.data?.course===1&&c.data?.capacity===12),'create payload');
        await click('Schedule session',room);
        await submit('Session schedule (local time)',{'Session title':'Practice','Starts':'2026-11-01T14:00','Ends':'2026-11-01T15:00'});
        check(calls.some(c=>c.path.endsWith('/9/sessions/')&&c.data?.lesson===2&&c.data?.scheduled_start.endsWith('Z')),'schedule timezone payload');
        const inviteForm=[...document.querySelectorAll('details')].find(d=>d.querySelector('summary').textContent==='Invite learner').querySelector('form');
        fill(inviteForm,'Recipient username','learner');await click('Search usernames',inviteForm);await click('@learner.name (Learner <img src=x>)',inviteForm);
        fill(inviteForm,'Recipient username','changed');
        await submit('Invite learner',{'Message':'Welcome'});
        check(!calls.some(c=>c.data?.recipient===42),'typing clears stale selection');
        fill(inviteForm,'Recipient username','learner');await click('Search usernames',inviteForm);await click('@learner.name (Learner <img src=x>)',inviteForm);
        await submit('Invite learner',{'Message':'Welcome'});
        check(calls.some(c=>c.path.endsWith('/9/users/')),'scoped username endpoint');
        check(calls.some(c=>c.path.endsWith('/9/invitations/')&&c.data?.recipient===42),'invitation payload');
        await click('Accept invitation');await click('Decline invitation');
        check(calls.some(c=>c.path.endsWith('/3/accept/'))&&calls.some(c=>c.path.endsWith('/3/decline/')),'recipient responses');
        await click('Sent invitations',room);await pause();await click('Revoke invitation',room);
        check(calls.some(c=>c.path.endsWith('/4/revoke/')),'revoke');
        const staffForm=[...document.querySelectorAll('details')].find(d=>d.querySelector('summary').textContent==='Add cohost').querySelector('form');
        fill(staffForm,'Cohost username','cohost');await click('Search usernames',staffForm);await click('@cohost.name (Cohost <img src=x>)',staffForm);
        await submit('Add cohost',{});
        await click('Refresh staff',room);await pause();await click('Remove cohost',room);await click('Make host',room);
        for(const role of ['COHOST','REMOVE','HOST'])check(calls.some(c=>c.path.endsWith('/9/staff/')&&c.data?.role===role),'staff '+role);
        check(!document.querySelector('img'),'user content stays plaintext');
        check(calls.filter(c=>c.data).every(c=>c.options.headers['X-CSRFToken']==='fixture-csrf'),'CSRF forwarded');
        check(document.documentElement.scrollWidth<=innerWidth+1,'mobile layout overflow');
        document.getElementById('result').textContent='PHASE_ONE_OK';
      })().catch(e=>document.getElementById('result').textContent='FAILED: '+e.message);
    `;
    const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:12px}${css}</style></head><body><input name="csrfmiddlewaretoken" value="fixture-csrf"><div id="classroom-management"></div><div class="vc-directory"><section id="room"></section><section id="learner"></section></div><pre id="result">RUNNING</pre><script>${fixture}</script><script>${script}</script><script>${assertions}</script></body></html>`;
    const file = join(temporary, 'test.html'); writeFileSync(file, html);
    const output = spawnSync(chrome, ['--headless=new','--disable-gpu','--disable-background-networking','--disable-extensions','--no-first-run',`--user-data-dir=${join(temporary,'profile')}`,'--window-size=390,844','--virtual-time-budget=5000','--dump-dom',pathToFileURL(file).href], {timeout:60000,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
    assert.equal(output.status,0,output.error?.message||output.stderr);
    assert.equal(output.stdout.match(/<pre id="result">([^<]*)<\/pre>/)?.[1],'PHASE_ONE_OK');
  } finally {
    assert.equal(dirname(temporary),root);
    assert.ok(temporary.startsWith(join(root,'.classroom-browser-test-phase1-')));
    rmSync(temporary,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
});
