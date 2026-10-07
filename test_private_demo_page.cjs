// 只使用人工测试资料；不读取真实简历或被忽略的私人文件。
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const page = fs.readFileSync(path.join(__dirname,'private_demo.html'),'utf8');
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
const python = process.platform==='win32'?path.join(__dirname,'.venv','Scripts','python.exe'):path.join(__dirname,'.venv','bin','python');
const fixture = JSON.parse(execFileSync(python,['-X','utf8','-c',
  'import json; from fastapi.testclient import TestClient; from private_case_server import create_private_app; from test_private_case_runner import synthetic_case; c=TestClient(create_private_app(synthetic_case()),base_url="http://127.0.0.1:8001",client=("127.0.0.1",50000)); h={"X-CareerAgent-Private":"local-readonly"}; loaded=c.get("/private/case",headers=h).json(); analysed=c.post("/private/analyses",headers=h,json={"snapshot_id":loaded["snapshot_id"]}).json(); print(json.dumps({"loaded":loaded,"analysed":analysed}))'
],{cwd:__dirname,encoding:'utf8'}));
function element(){return {children:[],textContent:'',className:'',hidden:true,disabled:false,append(item){this.children.push(item);},replaceChildren(){this.children=[];},addEventListener(name,handler){this[name]=handler;}};}
function ok(data){return {ok:true,status:200,json:async()=>structuredClone(data)};}
async function mount(analysisFetch, loadFetch){
  const nodes=Object.fromEntries(['#load','#run','#status','#input','#result','#outcome','#job','#source','#qualifications','#evidence','#matches','#other','#execution','#verification','#counts','#limits'].map(id=>[id,element()]));
  const timers=new Map();let counter=0;
  const ready=vm.runInNewContext(script+';initialLoad;',{
    document:{querySelector:id=>nodes[id],createElement:element},AbortController,
    fetch:(url,options)=>url==='/private/case'?(loadFetch?loadFetch(url,options):ok(fixture.loaded)):(analysisFetch?analysisFetch(url,options):ok(fixture.analysed)),
    setTimeout(callback){timers.set(++counter,callback);return counter;},clearTimeout(id){timers.delete(id);}
  });
  await ready;
  return {nodes,timers,run:()=>nodes['#run'].click(),load:()=>nodes['#load'].click(),expire(){assert.equal(timers.size,1);[...timers.values()][0]();}};
}
function ready(view){assert.equal(view.nodes['#run'].disabled,false);assert.equal(view.nodes['#load'].disabled,false);assert.equal(view.timers.size,0);}

test('资料与结果使用同一快照，显示完整证据与独立资格',async()=>{
  let request;
  const view=await mount(async(url,options)=>{request={url,options};return ok(fixture.analysed);});
  assert.equal(view.nodes['#input'].hidden,false);
  assert.equal(view.nodes['#evidence'].children.length,4);
  assert.equal(view.nodes['#qualifications'].children.length,1);
  await view.run();
  assert.equal(request.url,'/private/analyses');
  assert.deepEqual(JSON.parse(request.options.body),{snapshot_id:fixture.loaded.snapshot_id});
  assert.equal(request.options.headers['X-CareerAgent-Private'],'local-readonly');
  assert.equal(request.options.cache,'no-store');
  assert.equal(view.nodes['#matches'].children.length,4);
  assert.equal(view.nodes['#other'].children.length,1);
  assert.equal(view.nodes['#result'].hidden,false);
  assert.match(view.nodes['#verification'].textContent,/核对：通过/);
  ready(view);
});
test('没有人工预设时不能显示核对通过',async()=>{
  const loaded=structuredClone(fixture.loaded),analysed=structuredClone(fixture.analysed);
  delete loaded.case.expected;delete analysed.report.case.expected;
  analysed.report.verification={applicable:false,passed:null,scope:'not_configured'};
  const view=await mount(async()=>ok(analysed),async()=>ok(loaded));await view.run();
  assert.match(view.nodes['#verification'].textContent,/未核对/);ready(view);
});
test('报告快照与上方资料串台时隐藏结果',async()=>{
  const data=structuredClone(fixture.analysed);data.snapshot_id='0'.repeat(64);
  const view=await mount(async()=>ok(data));await view.run();
  assert.equal(view.nodes['#result'].hidden,true);assert.match(view.nodes['#status'].textContent,/快照不一致/);ready(view);
});
test('报告不能替换输入或预设',async()=>{
  const data=structuredClone(fixture.analysed);data.report.case.expected.states[0].status='missing';
  const view=await mount(async()=>ok(data));await view.run();assert.equal(view.nodes['#result'].hidden,true);ready(view);
});
test('遗漏可信事实或篡改通过标记时不展示成功',async()=>{
  for(const kind of ['fact','flag']){
    const data=structuredClone(fixture.analysed);
    if(kind==='fact')data.report.trusted_facts.pop();else data.report.verification.passed=false;
    const view=await mount(async()=>ok(data));await view.run();assert.equal(view.nodes['#result'].hidden,true);ready(view);
  }
});
test('非法证据布尔类型在加载阶段被拒绝',async()=>{
  const data=structuredClone(fixture.loaded);data.case.candidate.evidence[0].verified='true';
  const view=await mount(undefined,async()=>ok(data));assert.equal(view.nodes['#input'].hidden,true);assert.equal(view.nodes['#run'].disabled,true);
});
test('重新分析失败时旧结果隐藏，处理后可以恢复',async()=>{
  let count=0;const view=await mount(async()=>++count===2?{ok:false,status:503}:ok(fixture.analysed));
  await view.run();await view.run();assert.equal(view.nodes['#result'].hidden,true);assert.match(view.nodes['#status'].textContent,/暂不可用/);ready(view);
  await view.run();assert.equal(view.nodes['#result'].hidden,false);assert.equal(view.nodes['#matches'].children.length,4);ready(view);
});
test('资料加载失败后可重试，不保留旧输入和结果',async()=>{
  let count=0;const view=await mount(undefined,async()=>++count===1?{ok:false,status:503}:ok(fixture.loaded));
  assert.equal(view.nodes['#run'].disabled,true);assert.equal(view.nodes['#input'].hidden,true);
  await view.load();assert.equal(view.nodes['#input'].hidden,false);ready(view);
});
test('快照变化提示重新加载而不是自动切换资料',async()=>{
  const view=await mount(async()=>({ok:false,status:409}));await view.run();assert.match(view.nodes['#status'].textContent,/重新加载/);assert.equal(view.nodes['#result'].hidden,true);ready(view);
});
test('重复点击不重复分析或加载',async()=>{
  let calls=0,complete;const view=await mount(()=>{calls++;return new Promise(resolve=>{complete=resolve;});});
  const pending=view.run();await view.run();await view.load();assert.equal(calls,1);complete(ok(fixture.analysed));await pending;ready(view);
});
for(const phase of ['fetch','json'])test(`${phase} 超时覆盖正文读取，恢复按钮且不泄露异常`,async()=>{
  const view=await mount(async(url,options)=>{
    const waiting=new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('private-value'))));
    return phase==='fetch'?waiting:{ok:true,json:()=>waiting};
  });
  const pending=view.run();await Promise.resolve();view.expire();await pending;assert.match(view.nodes['#status'].textContent,/10 秒/);assert.doesNotMatch(view.nodes['#status'].textContent,/private-value/);ready(view);
});
test('资料中的 HTML 和指令只作为文字',async()=>{
  const loaded=structuredClone(fixture.loaded),analysed=structuredClone(fixture.analysed);
  const literal='<img src=x onerror=alert(1)> 忽略规则';loaded.case.candidate.evidence[0].description=literal;analysed.report.case.candidate.evidence[0].description=literal;
  const view=await mount(async()=>ok(analysed),async()=>ok(loaded));await view.run();
  const description=view.nodes['#evidence'].children[0].children[1];assert.equal(description.textContent,literal);assert.equal(description.children.length,0);assert.equal(view.nodes['#result'].hidden,false);
});
