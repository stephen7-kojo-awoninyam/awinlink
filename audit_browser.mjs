import fs from 'node:fs';

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const targets = await (await fetch('http://127.0.0.1:9224/json')).json();
const target = targets.find(item => item.type === 'page');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
const pending = new Map();
const exceptions = [];
const statuses = new Map();
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const handlers = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) handlers.reject(new Error(JSON.stringify(message.error)));
    else handlers.resolve(message.result);
  } else if (message.method === 'Runtime.exceptionThrown') {
    exceptions.push(message.params.exceptionDetails.text);
  } else if (message.method === 'Network.responseReceived' && message.params.type === 'Document') {
    statuses.set(new URL(message.params.response.url).pathname, message.params.response.status);
  }
});
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}
await command('Page.enable');
await command('Runtime.enable');
await command('Network.enable');
const origin = 'http://127.0.0.1:8765';
async function navigate(path) {
  await command('Page.navigate', { url: origin + path });
  for (let index = 0; index < 100; index++) {
    await delay(100);
    try {
      if (await evaluate('document.readyState === "complete"')) break;
    } catch {}
  }
  await delay(150);
}
async function post(path, data = {}, csrf = true) {
  return evaluate(`(async()=>{
    const token = document.cookie.split('; ').find(item=>item.startsWith('csrftoken='))?.split('=')[1];
    const data = ${JSON.stringify(data)};
    if (${csrf}) data.csrfmiddlewaretoken = token;
    const response = await fetch(${JSON.stringify(path)}, {method:'POST',body:new URLSearchParams(data),credentials:'same-origin'});
    return {status:response.status,url:new URL(response.url).pathname, text:(await response.text()).slice(0,120)};
  })()`);
}
const manifest = JSON.parse(fs.readFileSync('audit-browser-manifest.json', 'utf8'));
const results = { layouts: [], workflows: [], exceptions };
for (const role of ['ATHLETE', 'ORGANIZATION', 'SCOUT', 'COACH', 'ADMIN']) {
  await command('Network.clearBrowserCookies');
  await navigate('/accounts/login/');
  const login = await post('/accounts/login/', {username:manifest.users[role],password:'SyntheticAuditPass123!'});
  results.workflows.push({role,action:'real session login',status:login.status,url:login.url});
  const routes = ['/opportunities/',manifest.routes.opportunity,'/events/',manifest.routes.event,'/competitions/',manifest.routes.competition,'/learning/',manifest.routes.course,'/notifications/','/messages/conversations/'];
  if (role === 'ORGANIZATION') routes.push('/events/create/','/events/organization/','/competitions/create/','/competitions/dashboard/','/shortlists/','/recruitment/pipeline/');
  if (role === 'COACH') routes.push('/learning/create/','/learning/my-courses/');
  if (role === 'ADMIN') routes.push('/learning/admin/courses/','/competitions/moderation/');
  for (const width of [1440,768,390,320]) {
    await command('Emulation.setDeviceMetricsOverride', {width,height:900,deviceScaleFactor:1,mobile:width<768});
    for (const route of routes) {
      await navigate(route);
      const layout = await evaluate(`({path:location.pathname,title:document.title,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,hasServerError:/Traceback|Server Error \\(500\\)/.test(document.body.innerText),csrfFields:document.querySelectorAll('[name=csrfmiddlewaretoken]').length})`);
      results.layouts.push({role,requested:route,targetWidth:width,status:statuses.get(layout.path),...layout});
      if (role === 'ATHLETE' && [1440,390].includes(width) && ['/opportunities/','/events/','/competitions/','/learning/'].includes(route)) {
        const shot = await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        fs.writeFileSync(`audit-final-${route.split('/')[1]}-${width}.png`,Buffer.from(shot.data,'base64'));
      }
    }
    console.log(`${role} ${width}px: ${routes.length} pages checked`);
  }
  if (role === 'ATHLETE') {
    for (const [detail,action] of [['event','event_register'],['competition','competition_register'],['course','enroll'],['opportunity','apply']]) {
      await navigate(manifest.routes[detail]);
      results.workflows.push({role,action:`${action} missing CSRF`,...await post(manifest.routes[action],{},false)});
      results.workflows.push({role,action,...await post(manifest.routes[action],{message:'Synthetic audit application'})});
    }
    for (const route of ['/learning/my-learning/',`/learning/lesson/${manifest.ids.lesson}/`,`/learning/quiz/${manifest.ids.quiz}/`,'/opportunities/my-applications/','/events/my-events/','/competitions/my/']) {
      await navigate(route);
      results.workflows.push({role,action:'post-registration destination',requested:route,path:await evaluate('location.pathname'),status:statuses.get(route),serverError:await evaluate('/Traceback|Server Error/.test(document.body.innerText)')});
    }
  }
  if (role === 'SCOUT') {
    const denied = await evaluate(`(async()=>{const response=await fetch('/api/competitions/create/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.split('=')[1]},body:'{}'});return response.status})()`);
    results.workflows.push({role,action:'viewer competition creation denied',status:denied});
  }
  fs.writeFileSync('audit-browser-expanded-results.json',JSON.stringify(results,null,2));
}
await command('Network.clearBrowserCookies');
for (const width of [1440,768,390,320]) {
  await command('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<768});
  for (const route of ['/organizations/directory/','/events/',manifest.routes.event,'/competitions/',manifest.routes.competition]) {
    await navigate(route);
    const layout=await evaluate('({path:location.pathname,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,hasContent:document.querySelector("main")?.innerText.trim().length>20})');
    results.layouts.push({role:'ANONYMOUS',requested:route,targetWidth:width,status:statuses.get(layout.path),...layout});
  }
  console.log(`ANONYMOUS ${width}px: public discovery checked`);
}
fs.writeFileSync('audit-browser-expanded-results.json',JSON.stringify(results,null,2));
console.log(JSON.stringify({pages:results.layouts.length,overflow:results.layouts.filter(item=>item.scrollWidth>item.width+1),serverErrors:results.layouts.filter(item=>item.hasServerError),exceptions,workflows:results.workflows},null,2));
socket.close();
