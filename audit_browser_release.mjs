import fs from 'node:fs';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const target=(await (await fetch('http://127.0.0.1:9224/json')).json()).find(item=>item.type==='page');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}));
let id=0;const pending=new Map();const statuses=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){pending.get(message.id)(message.result);pending.delete(message.id);}else if(message.method==='Network.responseReceived'&&message.params.type==='Document')statuses.set(new URL(message.params.response.url).pathname,message.params.response.status);});
const command=(method,params={})=>new Promise(resolve=>{const next=++id;pending.set(next,resolve);socket.send(JSON.stringify({id:next,method,params}));});
const evaluate=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
async function navigate(path){await command('Page.navigate',{url:'http://127.0.0.1:8765'+path});for(let attempt=0;attempt<80;attempt++){await delay(100);try{if(await evaluate(`document.readyState==='complete'&&location.pathname===${JSON.stringify(path)}`))break;}catch{}}await delay(150);}
const results=JSON.parse(fs.readFileSync('audit-browser-expanded-results.json','utf8'));
results.layouts=results.layouts.filter(item=>item.requested!=='/recruitment/');
for(const [role,route]of [['ORGANIZATION','/recruitment/pipeline/'],['COACH','/coaches/saved-talents/']]){
 await command('Network.clearBrowserCookies');await navigate('/accounts/login/');
 await evaluate(`(async()=>{const token=document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.split('=')[1];const response=await fetch('/accounts/login/',{method:'POST',body:new URLSearchParams({username:'audit_${role.toLowerCase()}',password:'SyntheticAuditPass123!',csrfmiddlewaretoken:token})});return response.status;})()`);
 for(const width of [1440,768,390,320]){
  await command('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<768});await navigate(route);
  const layout=await evaluate('({path:location.pathname,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,hasServerError:/Traceback|Server Error/.test(document.body.innerText),postForms:document.querySelectorAll("form[method=post]").length})');
  results.layouts.push({role,requested:route,targetWidth:width,status:statuses.get(layout.path),...layout});
 }
}
fs.writeFileSync('audit-browser-release-results.json',JSON.stringify(results,null,2));
const bad=results.layouts.filter(item=>item.status!==200||item.width!==item.targetWidth||item.scrollWidth>item.width+1||item.hasServerError);
console.log(JSON.stringify({pages:results.layouts.length,bad,exceptions:results.exceptions},null,2));socket.close();
