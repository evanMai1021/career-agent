// 虚构响应与页面替身；不读取真实资料或访问网络。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const page=fs.readFileSync(path.join(__dirname,'file_import.html'),'utf8');
const script=page.match(/<script>([\s\S]*?)<\/script>/)[1];
const fixture={format:'txt',segments:[{location:'第 1 行',text:'虚构 Python 学习😀'},{location:'第 2 行',text:''}],warnings:['只是文字预览'],verification:'unverified',analysis_performed:false,saved:false};
function element(){return {children:[],textContent:'',hidden:false,disabled:false,value:'',files:[],append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},addEventListener(event,handler){this[event]=handler;}};}
function ok(data=fixture){return {ok:true,status:200,json:async()=>structuredClone(data)};}
function mount(fetchImpl=async()=>ok(),modelEnabled=false){
  const nodes=Object.fromEntries(['#file','#extract','#clear','#preview','#status','#segments','#warnings','#review','#confirm','#format-mode','#model-options','#text-kind','#additional','#data-kind','#case-id','#model-consent','#format-json','#format-status','#json-result','#json-draft','#json-status','#validate-json','#model-availability','#regenerate-warning','#regenerate-confirm','#regenerate-cancel','#json-completeness-status','#json-sections'].map(id=>[id,element()]));
  nodes['#preview'].hidden=true;
  nodes['#regenerate-warning'].hidden=true;
  nodes['#format-mode'].value='text';nodes['#text-kind'].value='resume';nodes['#data-kind'].value='synthetic_private_test';nodes['#case-id'].value='formatted_draft';nodes['#model-consent'].checked=false;nodes['#model-options'].hidden=true;nodes['#json-result'].hidden=true;
  const timers=new Map();let next=0;
  vm.runInNewContext(script.replace('const MODEL_ENABLED=false;',`const MODEL_ENABLED=${modelEnabled};`),{document:{querySelector:id=>nodes[id],createElement:element},AbortController,
    fetch:fetchImpl,setTimeout(callback){timers.set(++next,callback);return next;},clearTimeout(id){timers.delete(id);}});
  const view={nodes,timers,choose(name='synthetic.txt',size=25){nodes['#file'].files=[{name,size}];nodes['#file'].change();},run:()=>nodes['#extract'].click(),clear:()=>nodes['#clear'].click(),confirm:()=>nodes['#confirm'].click(),format:()=>nodes['#format-json'].click(),validate:()=>nodes['#validate-json'].click(),enable(){nodes['#format-mode'].value='model';nodes['#format-mode'].change();view.confirm();nodes['#model-consent'].checked=true;nodes['#model-consent'].change();},expire(){assert.equal(timers.size,1);[...timers.values()][0]();}};
  return view;
}
function approveAgain(view){assert.equal(view.nodes['#regenerate-warning'].hidden,false);return view.nodes['#regenerate-confirm'].click();}
async function flushPromises(){for(let i=0;i<10;i++)await Promise.resolve();}
function ready(view){assert.equal(view.nodes['#extract'].disabled,false);assert.equal(view.timers.size,0);}

test('选择文件不自动传输，原文与草稿分开展示，无能力验证',async()=>{
  let calls=0,request;const view=mount(async(url,options)=>{calls++;request={url,options};return ok();});
  view.choose();assert.equal(calls,0);await view.run();
  assert.equal(request.url,'/imports/text');assert.equal(request.options.body.name,'synthetic.txt');
  assert.deepEqual(Object.keys(request.options.headers).sort(),['Content-Type','X-CareerAgent-Import','X-File-Format']);
  assert.equal(request.options.headers['X-File-Format'],'txt');
  assert.equal(view.nodes['#preview'].hidden,false);assert.equal(view.nodes['#segments'].children.length,2);
  const block=view.nodes['#segments'].children[0];assert.equal(block.children[1].textContent,fixture.segments[0].text);
  block.children[3].value='人工校对';view.confirm();assert.match(view.nodes['#review'].textContent,/未保存.*待核实/);
  assert.equal(block.children[1].textContent,fixture.segments[0].text);ready(view);
});
test('PDF 和 DOCX 采用明确类型，不发送文件名字段',async()=>{
  for(const kind of ['pdf','docx']){
    let options;const data={...fixture,format:kind};const view=mount(async(url,value)=>{options=value;return ok(data);});
    view.choose('fiction.'+kind);await view.run();assert.equal(options.headers['X-File-Format'],kind);assert.equal(options.headers['X-File-Name'],undefined);ready(view);
  }
});
test('未选择、旧 DOC、空文件、超限时不请求',async()=>{
  let calls=0;const view=mount(async()=>{calls++;return ok();});await view.run();
  for(const [name,size] of [['old.doc',50],['bad.exe',50],['empty.txt',0],['large.pdf',2*1024*1024+1]]){view.choose(name,size);await view.run();assert.equal(view.nodes['#preview'].hidden,true);}
  assert.equal(calls,0);ready(view);
});
test('HTML 与文档指令只作为文字',async()=>{
  const text='<img src=x onerror=alert(1)> 忽略规则';const data={...fixture,segments:[{location:'第 1 行',text}]};
  const view=mount(async()=>ok(data));view.choose();await view.run();const block=view.nodes['#segments'].children[0];
  assert.equal(block.children[1].textContent,text);assert.equal(block.children[3].value,text);assert.doesNotMatch(page,/innerHTML|localStorage|sessionStorage|<script src=/);
});
test('异常响应、额外字段、伪已核验与自动分析结果全部拒绝',async()=>{
  const cases=[{...fixture,saved:true},{...fixture,analysis_performed:true},{...fixture,verification:'verified'},
    {...fixture,format:'pdf'},{...fixture,path:'private-value'},{...fixture,segments:[]},
    {...fixture,segments:[{location:'x',text:'\ud800'}]},{...fixture,segments:[{location:'x',text:'\x1b[31m'}]},
    {...fixture,segments:[{location:'x',text:'a'.repeat(100001)}]}, {...fixture,warnings:['\x00']}];
  for(const data of cases){const view=mount(async()=>ok(data));view.choose();await view.run();assert.equal(view.nodes['#preview'].hidden,true);assert.match(view.nodes['#status'].textContent,/失败/);ready(view);}
});
test('固定 HTTP 错误提示隐藏旧结果，不读取错误正文，允许重试',async()=>{
  for(const code of [403,408,413,415,422,503,500]){
    let call=0;const view=mount(async()=>++call===2?{ok:false,status:code,json(){throw new Error('private-value');}}:ok());
    view.choose();await view.run();await view.run();assert.equal(view.nodes['#preview'].hidden,true);assert.doesNotMatch(view.nodes['#status'].textContent,/private-value/);ready(view);
    await view.run();assert.equal(view.nodes['#preview'].hidden,false);ready(view);
  }
});
test('断连和非 JSON 响应不泄露异常',async()=>{
  for(const fetchImpl of [async()=>{throw new Error('private-path');},async()=>({ok:true,json:async()=>{throw new Error('private-content');}})]){
    const view=mount(fetchImpl);view.choose();await view.run();assert.equal(view.nodes['#preview'].hidden,true);assert.doesNotMatch(view.nodes['#status'].textContent,/private/);ready(view);
  }
});
for(const phase of ['fetch','json'])test(`${phase} 等待超时覆盖正文读取且恢复按钮`,async()=>{
  const view=mount(async(url,options)=>{
    const waiting=new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('private-timeout'))));
    return phase==='fetch'?waiting:{ok:true,json:()=>waiting};
  });view.choose();const pending=view.run();await Promise.resolve();view.expire();await pending;
  assert.match(view.nodes['#status'].textContent,/30 秒/);assert.equal(view.nodes['#preview'].hidden,true);ready(view);
});
test('重复点击只发送一次',async()=>{
  let calls=0,complete;const view=mount(()=>{calls++;return new Promise(resolve=>{complete=resolve;});});
  view.choose();const pending=view.run();await view.run();assert.equal(calls,1);complete(ok());await pending;ready(view);
});
test('取消后旧请求晚返回不能恢复已清空的结果',async()=>{
  let complete;const view=mount(()=>new Promise(resolve=>{complete=resolve;}));view.choose();const pending=view.run();view.clear();complete(ok());await pending;
  assert.equal(view.nodes['#preview'].hidden,true);assert.equal(view.nodes['#file'].value,'');assert.match(view.nodes['#status'].textContent,/已清空/);ready(view);
});
test('换文件并重试，旧请求不能覆盖新结果',async()=>{
  let first,call=0;const newer={...fixture,segments:[{location:'第 1 行',text:'新虚构资料'}]};
  const view=mount(()=>++call===1?new Promise(resolve=>{first=resolve;}):ok(newer));view.choose();const old=view.run();view.choose('new.txt');await view.run();first(ok());await old;
  assert.equal(view.nodes['#segments'].children[0].children[1].textContent,'新虚构资料');ready(view);
});
test('再次修改校对草稿撤销确认，空白与控制字符不能确认',async()=>{
  const view=mount();view.choose();await view.run();view.confirm();assert.match(view.nodes['#review'].textContent,/已确认/);
  const editor=view.nodes['#segments'].children[0].children[3];editor.value='再修改';editor.input();assert.match(view.nodes['#review'].textContent,/重新确认/);
  for(const value of ['','\x00','x'.repeat(100001)]){editor.value=value;view.confirm();assert.doesNotMatch(view.nodes['#review'].textContent,/已确认/);}
});
test('清空删除所有草稿与来源，确认按钮不能产生结果',async()=>{
  const view=mount();view.choose();await view.run();view.confirm();view.clear();view.confirm();assert.equal(view.nodes['#segments'].children.length,0);assert.equal(view.nodes['#warnings'].children.length,0);assert.equal(view.nodes['#preview'].hidden,true);assert.doesNotMatch(view.nodes['#review'].textContent,/已确认/);ready(view);
});

const jsonFixture={draft:{case_id:'formatted_draft',data_kind:'synthetic_private_test',notice:'模型整理，待复核',job:null,candidate:{username:'draft_candidate',evidence:[{evidence_id:'ev_001',skill_id:'python',description:'虚构 Python 学习😀',level:'learning',source:'校对文字',verified:false}]},qualifications:[]},schema_valid:false,missing_sections:['job'],verification:'unverified',analysis_performed:false,saved:false,model_generated:true,usage:{input_tokens:50,output_tokens:30}};
async function modelView(modelFetch,enabled=true){const view=mount(async(url,options)=>url==='/imports/text'?ok():(modelFetch?modelFetch(url,options):ok(jsonFixture)),enabled);view.choose();await view.run();return view;}
test('默认关闭模型；仅选择或校对文字不外发',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);},false);view.enable();await view.format();assert.equal(calls,0);assert.match(view.nodes['#format-status'].textContent,/启用/);assert.equal(view.nodes['#json-result'].hidden,true);
});
test('发送的是修改后的文字，缺少 JD 明确为 null，所有声明仍待核实',async()=>{
  let request;const view=await modelView(async(url,options)=>{request={url,payload:JSON.parse(options.body)};return ok(jsonFixture);});
  const editor=view.nodes['#segments'].children[0].children[3];editor.value='修改后的虚构练习';editor.input();view.enable();await view.format();
  assert.equal(request.url,'/imports/format-json');assert.equal(request.payload.segments[0].text,'修改后的虚构练习');assert.equal(request.payload.consent,true);assert.equal(request.payload.review_confirmed,true);assert.equal(request.payload.additional_text,'');
  assert.equal(view.nodes['#json-result'].hidden,false);assert.match(view.nodes['#json-status'].textContent,/缺少.*JD/);assert.equal(JSON.parse(view.nodes['#json-draft'].value).candidate.evidence[0].verified,false);assert.equal(JSON.parse(view.nodes['#json-draft'].value).job,null);assert.equal(view.timers.size,0);
});
test('未同意外发或未确认校对不调用模型',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});view.nodes['#format-mode'].value='model';view.nodes['#format-mode'].change();await view.format();
  view.confirm();await view.format();assert.equal(calls,0);
});
test('再次改文字、补充信息或来源设置撤销校对和外发同意',async()=>{
  const view=await modelView();view.enable();await view.format();
  view.nodes['#additional'].value='新的模拟 JD';view.nodes['#additional'].input();assert.equal(view.nodes['#model-consent'].checked,false);assert.equal(view.nodes['#json-result'].hidden,true);assert.match(view.nodes['#review'].textContent,/重新确认/);await view.format();assert.match(view.nodes['#format-status'].textContent,/确认/);
});
test('修改主要校对文字撤销旧外发同意；重新校对仍需重新勾选',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});
  view.enable();await view.format();assert.equal(calls,1);
  const editor=view.nodes['#segments'].children[0].children[3];editor.value='新的脱敏校对文字';editor.input();
  assert.equal(view.nodes['#model-consent'].checked,false);assert.equal(view.nodes['#json-result'].hidden,true);
  view.confirm();await view.format();assert.equal(calls,1);
  view.nodes['#model-consent'].checked=true;view.nodes['#model-consent'].change();await view.format();assert.equal(calls,1);await approveAgain(view);assert.equal(calls,2);
});
test('完整 JSON 仍仅为结构通过，无分析或保存',async()=>{
  const data=structuredClone(jsonFixture);data.draft.job={job_id:'draft_job',title:'模拟岗位',requirements:[{requirement_id:'req_001',skill_id:'python',description:'模拟要求',category:'required',priority:2}]};data.schema_valid=true;data.missing_sections=[];
  const view=await modelView(async()=>ok(data));view.enable();await view.format();assert.match(view.nodes['#json-status'].textContent,/结构通过.*人工核对.*没有保存或分析/);assert.doesNotMatch(view.nodes['#json-status'].textContent,/能力已验证/);
});
test('编辑 JSON 后只校验当前草稿，不再调用模型',async()=>{
  const calls=[];let edited;
  const view=await modelView(async(url,options)=>{calls.push(url);if(url==='/imports/format-json')return ok(jsonFixture);edited=JSON.parse(options.body).draft;const data=structuredClone(jsonFixture);delete data.model_generated;delete data.usage;data.draft=edited;return ok(data);});
  view.enable();await view.format();const draft=JSON.parse(view.nodes['#json-draft'].value);draft.candidate.evidence[0].description='手动调整';view.nodes['#json-draft'].value=JSON.stringify(draft);view.nodes['#json-draft'].input();assert.match(view.nodes['#json-status'].textContent,/重新校验/);await view.validate();
  assert.deepEqual(calls,['/imports/format-json','/imports/validate-json']);assert.equal(edited.candidate.evidence[0].description,'手动调整');assert.match(view.nodes['#json-status'].textContent,/缺少/);
});

test('编辑 JSON 校验保留原始重复键与非有限数，不静默改写',async()=>{
  const original=JSON.stringify(jsonFixture.draft);
  const invalid=[original.replace('{','{"case_id":"other_draft",'),
    original.replace('"notice":"模型整理，待复核"','"notice":1e400')];
  for(const raw of invalid){
    let body;
    const view=await modelView(async(url,options)=>{
      if(url==='/imports/format-json')return ok(jsonFixture);
      body=options.body;return {ok:false,status:422};
    });
    view.enable();await view.format();view.nodes['#json-draft'].value=raw;view.nodes['#json-draft'].input();await view.validate();
    assert.equal(body,'{"draft":'+raw+'}');
    assert.equal(view.nodes['#json-draft'].value,raw);
    assert.match(view.nodes['#json-status'].textContent,/未通过/);
    assert.doesNotMatch(view.nodes['#json-status'].textContent,/结构通过/);
  }
});
test('语法错误 JSON 不发请求；非法升级验证结果不展示为通过',async()=>{
  let calls=0;const data=structuredClone(jsonFixture);data.draft.candidate.evidence[0].verified=true;
  const view=await modelView(async()=>{calls++;return ok(data);});view.enable();await view.format();assert.equal(view.nodes['#json-result'].hidden,true);assert.match(view.nodes['#format-status'].textContent,/异常/);
  const valid=await modelView();valid.enable();await valid.format();valid.nodes['#json-draft'].value='{broken';valid.nodes['#json-draft'].input();await valid.validate();assert.match(valid.nodes['#json-status'].textContent,/语法无效/);assert.equal(calls,1);
});
test('模型结果多字段、错误缺项标记和假已保存均拒绝',async()=>{
  for(const change of [data=>data.saved=true,data=>data.model_generated=false,data=>data.schema_valid=true,data=>data.missing_sections=[],data=>data.path='private-value',data=>data.usage.input_tokens='private-value']){
    const data=structuredClone(jsonFixture);change(data);const view=await modelView(async()=>ok(data));view.enable();await view.format();assert.equal(view.nodes['#json-result'].hidden,true);assert.doesNotMatch(view.nodes['#format-status'].textContent,/private/);
  }
});
test('模型请求失败隐藏旧 JSON，不显示异常正文，可重试',async()=>{
  let call=0;const view=await modelView(async()=>++call===2?{ok:false,status:503,json(){throw new Error('private-key');}}:ok(jsonFixture));view.enable();await view.format();await view.format();await approveAgain(view);assert.equal(view.nodes['#json-result'].hidden,true);assert.match(view.nodes['#format-status'].textContent,/密钥/);assert.doesNotMatch(view.nodes['#format-status'].textContent,/private-key/);await view.format();await approveAgain(view);assert.equal(view.nodes['#json-result'].hidden,false);
});
test('取消模型整理或修改文字，晚返回 JSON 不恢复旧结果',async()=>{
  for(const action of ['clear','edit']){
    let complete;const view=await modelView(()=>new Promise(resolve=>{complete=resolve;}));view.enable();const pending=view.format();if(action==='clear')view.clear();else view.nodes['#segments'].children[0].children[3].input();complete(ok(jsonFixture));await pending;assert.equal(view.nodes['#json-result'].hidden,true);assert.equal(view.nodes['#json-draft'].value,'');assert.equal(view.timers.size,0);
  }
});
test('重复点击模型请求只调用一次',async()=>{
  let calls=0,complete;const view=await modelView(()=>{calls++;return new Promise(resolve=>{complete=resolve;});});view.enable();const pending=view.format();await view.format();assert.equal(calls,1);complete(ok(jsonFixture));await pending;assert.equal(view.timers.size,0);
});
for(const phase of ['fetch','json'])test(`模型 ${phase} 超时不给假成功并提示潜在费用`,async()=>{
  const view=await modelView(async(url,options)=>{const waiting=new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('private-key'))));return phase==='fetch'?waiting:{ok:true,json:()=>waiting};});
  view.enable();const pending=view.format();await Promise.resolve();view.expire();await pending;assert.match(view.nodes['#format-status'].textContent,/45 秒.*用量/);assert.doesNotMatch(view.nodes['#format-status'].textContent,/private-key/);assert.equal(view.nodes['#json-result'].hidden,true);assert.equal(view.timers.size,0);
});
test('校对文本超限或非法匿名标识不发送模型请求',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});view.enable();view.nodes['#case-id'].value='个人姓名';await view.format();view.nodes['#case-id'].value='draft_case';view.nodes['#segments'].children[0].children[3].value='x'.repeat(12001);await view.format();assert.equal(calls,0);assert.match(view.nodes['#format-status'].textContent,/12000/);
});

test('JSON 编辑区域加高、等宽且可调整，不影响正文校对框',()=>{
  assert.match(page,/#json-draft\{min-height:480px;[^}]*Consolas[^}]*monospace;resize:vertical/);
  assert.match(page,/@media\(max-width:600px\)\{#json-draft\{min-height:360px/);
  assert.match(page,/textarea\{[^}]*system-ui,sans-serif/);
});
test('每个必需部分单独列出，null 缺项不宣称完整',async()=>{
  for(const missing of [['job'],['candidate'],['job','candidate'],[]]){
    const data=structuredClone(jsonFixture);
    data.draft.job=missing.includes('job')?null:{job_id:'draft_job',title:'模拟岗位',requirements:[{requirement_id:'req_001',skill_id:'python',description:'模拟要求',category:'required',priority:2}]};
    if(missing.includes('candidate'))data.draft.candidate=null;
    data.missing_sections=missing;data.schema_valid=missing.length===0;
    const view=await modelView(async()=>ok(data));view.enable();await view.format();
    const rows=view.nodes['#json-sections'].children.map(item=>item.textContent);
    assert.equal(rows.length,2);
    assert.equal(rows.filter(row=>row.includes('缺少')).length,missing.length);
    for(const key of missing)assert.ok(rows.some(row=>row.includes(key+' = null')));
    assert.match(view.nodes['#json-completeness-status'].textContent,missing.length?/暂不能用于分析/:/仅结构通过.*待核实/);
  }
});
test('编辑、语法错误及字段失败清除旧缺项结论，不清除可修改 JSON',async()=>{
  const view=await modelView(async(url)=>url==='/imports/format-json'?ok(jsonFixture):{ok:false,status:422,json:async()=>({error_code:'json'})});
  view.enable();await view.format();assert.equal(view.nodes['#json-sections'].children.length,2);
  view.nodes['#json-draft'].value='{broken';view.nodes['#json-draft'].input();await view.validate();
  assert.equal(view.nodes['#json-sections'].children.length,0);assert.match(view.nodes['#json-completeness-status'].textContent,/待确认/);
  view.nodes['#json-draft'].value=JSON.stringify(jsonFixture.draft);await view.validate();
  assert.equal(view.nodes['#json-sections'].children.length,0);assert.match(view.nodes['#json-status'].textContent,/字段检查未通过/);
  assert.equal(view.nodes['#json-result'].hidden,false);
});
test('本地重新校验更新缺项展示，不调用模型或弹出收费确认',async()=>{
  const calls=[];const view=await modelView(async(url,options)=>{
    calls.push(url);if(url==='/imports/format-json')return ok(jsonFixture);
    return ok({draft:JSON.parse(options.body).draft,missing_sections:['job','candidate'],schema_valid:false,verification:'unverified',analysis_performed:false,saved:false});
  });
  view.enable();await view.format();const value=structuredClone(jsonFixture.draft);value.candidate=null;
  view.nodes['#json-draft'].value=JSON.stringify(value);view.nodes['#json-draft'].input();await view.validate();
  assert.equal(view.nodes['#json-sections'].children.filter(row=>row.textContent.includes('缺少')).length,2);
  assert.deepEqual(calls,['/imports/format-json','/imports/validate-json']);assert.equal(view.nodes['#regenerate-warning'].hidden,true);
});
test('固定类别区分隐私、输入字段、JSON 字段、模型引用与输出结构，不回显正文',async()=>{
  for(const [code,pattern] of [['privacy',/隐私检查/],['input',/请求字段检查/],['json',/JSON 字段检查/],['quote',/模型引用检查/],['output',/模型结果字段或结构/]]){
    const view=await modelView(async()=>({ok:false,status:422,json:async()=>({error_code:code,detail:'private-key original-text'})}));
    view.enable();await view.format();assert.match(view.nodes['#format-status'].textContent,pattern);
    assert.doesNotMatch(view.nodes['#format-status'].textContent,/private-key|original-text/);assert.equal(view.nodes['#json-result'].hidden,true);
  }
});
test('未知类别、危险键、状态不符及非法正文均降级为固定提示',async()=>{
  for(const body of [{error_code:'private-key'},{error_code:'__proto__'},{error_code:'toString'},{error_code:'model'},null,'original-text']){
    const view=await modelView(async()=>({ok:false,status:422,json:async()=>body}));view.enable();await view.format();
    assert.match(view.nodes['#format-status'].textContent,/可识别的错误类别/);assert.doesNotMatch(view.nodes['#format-status'].textContent,/private-key|original-text|__proto__/);
  }
});
test('错误正文读取同样受 45 秒限制且不泄露读取异常',async()=>{
  const view=await modelView(async(url,options)=>({ok:false,status:422,json:()=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('private-key'))))}));
  view.enable();const pending=view.format();await flushPromises();view.expire();await pending;
  assert.match(view.nodes['#format-status'].textContent,/45 秒.*用量/);assert.doesNotMatch(view.nodes['#format-status'].textContent,/private-key/);assert.equal(view.timers.size,0);
});
test('取消后错误正文晚返回不污染新页面',async()=>{
  let complete;const view=await modelView(async()=>({ok:false,status:422,json:()=>new Promise(resolve=>{complete=resolve;})}));
  view.enable();const pending=view.format();await flushPromises();view.clear();complete({error_code:'privacy'});await pending;
  assert.equal(view.nodes['#format-status'].textContent,'');assert.equal(view.nodes['#preview'].hidden,true);
});
test('成功后再次点击只提示费用，取消保留手动 JSON 且不外发',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});view.enable();await view.format();
  view.nodes['#json-draft'].value+='\n';view.nodes['#json-draft'].input();const old=view.nodes['#json-draft'].value;
  await view.format();await view.format();assert.equal(calls,1);assert.equal(view.nodes['#json-draft'].value,old);assert.equal(view.nodes['#json-result'].hidden,false);
  assert.match(page,/可能再次产生 API 费用.*替换当前 JSON 草稿/);
  view.nodes['#regenerate-cancel'].click();assert.equal(view.nodes['#regenerate-warning'].hidden,true);assert.equal(view.nodes['#json-draft'].value,old);assert.equal(calls,1);
  assert.match(view.nodes['#format-status'].textContent,/未发起新的模型请求/);
});
test('明确再次生成仅发出一次请求，再次成功仍需要费用确认',async()=>{
  let calls=0,complete;const view=await modelView(async()=>++calls===1?ok(jsonFixture):new Promise(resolve=>{complete=resolve;}));
  view.enable();await view.format();await view.format();const pending=approveAgain(view);await view.nodes['#regenerate-confirm'].click();await view.format();assert.equal(calls,2);
  complete(ok(jsonFixture));await pending;await view.format();assert.equal(calls,2);assert.equal(view.nodes['#regenerate-warning'].hidden,false);assert.equal(view.timers.size,0);
});
test('待确认期间修改文字或 JSON、撤销同意及清空，旧确认均不能发送',async()=>{
  for(const action of ['text','json','consent','clear']){
    let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});view.enable();await view.format();await view.format();
    if(action==='text')view.nodes['#segments'].children[0].children[3].input();
    if(action==='json')view.nodes['#json-draft'].input();
    if(action==='consent'){view.nodes['#model-consent'].checked=false;view.nodes['#model-consent'].change();}
    if(action==='clear')view.clear();
    assert.equal(view.nodes['#regenerate-warning'].hidden,true);await view.nodes['#regenerate-confirm'].click();assert.equal(calls,1);
  }
});
test('换文件后首次生成不沿用旧收费确认状态',async()=>{
  let calls=0;const view=await modelView(async()=>{calls++;return ok(jsonFixture);});view.enable();await view.format();await view.format();
  view.choose('new.txt');await view.run();view.enable();await view.format();assert.equal(calls,2);assert.equal(view.nodes['#regenerate-warning'].hidden,true);
});
