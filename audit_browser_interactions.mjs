import fs from 'node:fs';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const target=(await (await fetch('http://127.0.0.1:9224/json')).json()).find(item=>item.type==='page');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));
let id=0; const pending=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){pending.get(message.id)(message.result);pending.delete(message.id);}});
const command=(method,params={})=>new Promise(resolve=>{const next=++id;pending.set(next,resolve);socket.send(JSON.stringify({id:next,method,params}));});
const evaluate=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;};
await command('Page.enable'); await command('Runtime.enable');
await command('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});
async function navigate(path){await command('Page.navigate',{url:'http://127.0.0.1:8765'+path});await delay(900);}
const results=[];
await navigate('/accounts/login/');
await evaluate(`(()=>{document.querySelector('[name=username]').value='audit_athlete';document.querySelector('[name=password]').value='SyntheticAuditPass123!';document.querySelector('form').requestSubmit();})()`);
await delay(1200);
results.push({action:'DOM login form submission',path:await evaluate('location.pathname')});
await navigate('/events/');
results.push({action:'mobile drawer opens',passed:await evaluate(`(()=>{document.querySelector('#mobileSidebarToggle').click();return document.querySelector('#awinlinkSidebar').classList.contains('show')})()`)});
results.push({action:'Escape closes drawer',passed:await evaluate(`(()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return !document.querySelector('#awinlinkSidebar').classList.contains('show')})()`)});
results.push({action:'event discovery filter empty state',passed:await evaluate(`(()=>{const form=document.querySelector('[data-event-filters]');form.elements.search.value='NoSuchAuditEvent';form.requestSubmit();return [...document.querySelectorAll('[data-event-card]')].every(card=>card.hidden)&&!document.querySelector('[data-filter-empty]').hidden})()`)});
results.push({action:'event discovery reset',passed:await evaluate(`(()=>{const form=document.querySelector('[data-event-filters]');form.reset();form.elements.search.value='';form.dispatchEvent(new Event('change',{bubbles:true}));return [...document.querySelectorAll('[data-event-card]')].some(card=>!card.hidden)})()`)});
await navigate('/competitions/');
results.push({action:'competition refinements and reset',passed:await evaluate(`(()=>{const filters=document.querySelector('[data-competition-refinements]');const stage=filters.querySelector('[name=stage]');stage.value='results';stage.dispatchEvent(new Event('change',{bubbles:true}));const empty=[...document.querySelectorAll('[data-competition-results] [data-competition-card]')].every(card=>card.hidden);filters.querySelector('[data-clear-refinements]').click();return empty&&[...document.querySelectorAll('[data-competition-results] [data-competition-card]')].some(card=>!card.hidden)})()`)});
const manifest=JSON.parse(fs.readFileSync('audit-browser-manifest.json','utf8'));
await navigate(`/learning/quiz/${manifest.ids.quiz}/`);
await evaluate(`(()=>{const answer=document.querySelector('input[type=radio][value=A]');answer.checked=true;answer.form.requestSubmit()})()`);
await delay(1500);
results.push({action:'DOM quiz submission',passed:await evaluate('document.body.innerText.includes("Quiz passed!")')});
await navigate(`/learning/lesson/${manifest.ids.lesson}/`);
await evaluate(`(()=>{const form=document.querySelector('form[action="/learning/lesson/${manifest.ids.lesson}/complete/"]');if(form)form.requestSubmit()})()`);
let completed=false;
for(let attempt=0;attempt<40;attempt++){
  await delay(250);
  try{completed=await evaluate(`location.pathname==='/learning/lesson/${manifest.ids.lesson}/'&&!document.querySelector('form[action="/learning/lesson/${manifest.ids.lesson}/complete/"]')&&!!document.querySelector('.lc-status--complete')`);}catch{}
  if(completed)break;
}
results.push({action:'lesson completion uses web destination',passed:completed});
fs.writeFileSync('audit-browser-interactions.json',JSON.stringify(results,null,2));
console.log(JSON.stringify(results,null,2)); socket.close();
