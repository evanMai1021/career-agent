// 虚构响应与页面替身；不读取真实资料或访问网络。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const PROJECT_ROOT=path.resolve(__dirname,'../..');
const vm=require('node:vm');
const page=fs.readFileSync(path.join(PROJECT_ROOT,'web','file_import.html'),'utf8');
const script=page.match(/<script>([\s\S]*?)<\/script>/)[1];
const fixture={format:'txt',segments:[{location:'第 1 行',text:'虚构 Python 学习😀'},{location:'第 2 行',text:''}],warnings:['只是文字预览'],verification:'unverified',analysis_performed:false,saved:false};
function element(){return {children:[],textContent:'',hidden:false,disabled:false,value:'',files:[],clientHeight:480,clientWidth:900,focus(){this.focused=true;},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;},scrollIntoView(options){this.scrolled=options;},append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},addEventListener(event,handler){this[event]=handler;}};}
function ok(data=fixture){return {ok:true,status:200,json:async()=>structuredClone(data)};}
function mount(fetchImpl=async()=>ok(),modelEnabled=false){
  const nodes=Object.fromEntries(['#file','#extract','#clear','#preview','#status','#segments','#warnings','#review','#confirm','#format-mode','#model-options','#text-kind','#additional','#data-kind','#case-id','#model-consent','#format-json','#format-status','#json-result','#json-draft','#json-status','#validate-json','#model-availability','#regenerate-warning','#regenerate-confirm','#regenerate-cancel','#json-completeness-status','#json-sections'].map(id=>[id,element()]));
  nodes['#preview'].hidden=true;
  for(const id of ['#workflow-step','#format-help','#validate-help','#analyse-help','#field-errors','#field-location-status','#analysis-filter','#filter-status','#filter-empty'])nodes[id]=element();
  nodes['#field-errors'].hidden=true;
  for(const id of ['#analysis-consent','#analyse-json','#analysis-status','#analysis-result','#analysis-summary','#analysis-counts','#analysis-matches','#analysis-other','#analysis-qualifications','#analysis-limits'])nodes[id]=element();
  nodes['#analysis-result'].hidden=true;nodes['#analysis-consent'].disabled=true;nodes['#analysis-consent'].checked=false;nodes['#analyse-json'].disabled=true;
  nodes['#regenerate-warning'].hidden=true;
  nodes['#format-mode'].value='text';nodes['#text-kind'].value='resume';nodes['#data-kind'].value='synthetic_private_test';nodes['#case-id'].value='formatted_draft';nodes['#model-consent'].checked=false;nodes['#model-options'].hidden=true;nodes['#json-result'].hidden=true;
  const timers=new Map();let next=0;
  vm.runInNewContext(script.replace('const MODEL_ENABLED=false;',`const MODEL_ENABLED=${modelEnabled};`),{document:{querySelector:id=>nodes[id],createElement:element},AbortController,
    getComputedStyle:()=>({lineHeight:'23.1px',fontSize:'14px'}),fetch:fetchImpl,setTimeout(callback){timers.set(++next,callback);return next;},clearTimeout(id){timers.delete(id);}});
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
  const view=await modelView(async()=>ok(data));view.enable();await view.format();assert.match(view.nodes['#json-status'].textContent,/结构通过.*人工核对.*本步不保存或触发分析/);assert.doesNotMatch(view.nodes['#json-status'].textContent,/能力已验证/);
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

function completeFixture(){const data=structuredClone(jsonFixture);data.draft.job={job_id:'draft_job',title:'虚构 Python 岗位',requirements:[{requirement_id:'req_python',skill_id:'python',description:'虚构 Python 项目要求',category:'required',priority:2},{requirement_id:'req_git',skill_id:'git',description:'虚构 Git 要求',category:'required',priority:1}]};data.schema_valid=true;data.missing_sections=[];return data;}
function validationFixture(draft){return {draft,schema_valid:draft.job!==null&&draft.candidate!==null,missing_sections:['job','candidate'].filter(key=>draft[key]===null),verification:'unverified',analysis_performed:false,saved:false};}
function reportFixture(draft){const matches=draft.job.requirements.map(item=>{const related=draft.candidate.evidence.filter(value=>value.skill_id===item.skill_id);return {...item,status:related.length?'unverified':'missing',related_evidence_ids:related.map(value=>value.evidence_id)};});return {analysis_performed:true,saved:false,report:{case:structuredClone(draft),execution_status:'completed',analysis_mode:'offline_deterministic',model_generated:false,matches,trusted_facts:matches.map(item=>({requirement_id:item.requirement_id,skill_id:item.skill_id,status:item.status,related_evidence_ids:item.related_evidence_ids,verified_evidence_ids:[],unverified_evidence_ids:item.related_evidence_ids,origin:'python_deterministic_match'})),verification:{applicable:false,passed:null,scope:'not_configured'},limitations:['只使用虚构输入，不证明真实能力。']}};}
async function analysisView(handler){const requests=[];const view=await modelView(async(url,options)=>{const payload=JSON.parse(options.body);requests.push({url,options,payload});if(url==='/imports/format-json')return ok(completeFixture());if(url==='/imports/validate-json')return ok(validationFixture(payload.draft));return handler?handler(url,options,payload):ok(reportFixture(payload.draft));});view.requests=requests;view.enable();await view.format();view.analyse=()=>view.nodes['#analyse-json'].click();view.consent=()=>{view.nodes['#analysis-consent'].checked=true;view.nodes['#analysis-consent'].change();};return view;}

test('生成或校验都不会自动分析，完整复验和明确确认后只调用本机分析',async()=>{
  const view=await analysisView();assert.equal(view.nodes['#analysis-consent'].disabled,true);await view.analyse();assert.equal(view.requests.length,1);
  await view.validate();await view.analyse();assert.equal(view.requests.length,2);assert.equal(view.nodes['#analysis-consent'].disabled,false);assert.equal(view.nodes['#analyse-json'].disabled,true);
  view.consent();await view.analyse();assert.equal(view.requests.length,3);const request=view.requests[2];assert.equal(request.url,'/imports/analyses');assert.equal(request.payload.analysis_confirmed,true);assert.deepEqual(request.payload.draft,completeFixture().draft);assert.equal(request.options.headers['X-CareerAgent-Import'],'local-preview');
  assert.equal(view.nodes['#analysis-result'].hidden,false);assert.match(view.nodes['#analysis-counts'].textContent,/已匹配 0.*部分匹配 0.*待核实 1.*缺少证据 1/);assert.match(view.nodes['#analysis-status'].textContent,/不证明资料真实.*未调用模型/);assert.equal(view.nodes['#analysis-matches'].children.length,2);assert.equal(view.nodes['#analysis-other'].children[0].textContent,'没有未关联证据。');ready(view);
});
test('缺少岗位的草稿不能开启分析，JSON 编辑立即撤销旧结果与确认',async()=>{
  const view=await analysisView();await view.validate();view.consent();await view.analyse();const editor=view.nodes['#json-draft'];const partial=structuredClone(jsonFixture.draft);editor.value=JSON.stringify(partial);editor.input();assert.equal(view.nodes['#analysis-result'].hidden,true);assert.equal(view.nodes['#analysis-consent'].checked,false);await view.validate();assert.equal(view.nodes['#analysis-consent'].disabled,true);view.consent();await view.analyse();assert.equal(view.requests.filter(item=>item.url==='/imports/analyses').length,1);
});
test('再次校验失败不得沿用分析许可，正文或设置修改与清空也失效',async()=>{
  for(const action of ['syntax','text','setting','clear','file']){const view=await analysisView();await view.validate();view.consent();await view.analyse();if(action==='syntax'){view.nodes['#json-draft'].value='{';await view.validate();}if(action==='text')view.nodes['#segments'].children[0].children[3].input();if(action==='setting')view.nodes['#additional'].input();if(action==='clear')view.clear();if(action==='file')view.choose('new.txt');assert.equal(view.nodes['#analysis-result'].hidden,true);assert.equal(view.nodes['#analysis-consent'].checked,false);assert.equal(view.nodes['#analyse-json'].disabled,true);}
});
test('旧分析晚响应不能覆盖修改、撤销或清空后的页面',async()=>{
  for(const action of ['edit','revoke','clear']){let complete;const view=await analysisView((url,options,payload)=>new Promise(resolve=>{complete=()=>resolve(ok(reportFixture(payload.draft)));}));await view.validate();view.consent();const pending=view.analyse();if(action==='edit')view.nodes['#json-draft'].input();if(action==='revoke'){view.nodes['#analysis-consent'].checked=false;view.nodes['#analysis-consent'].change();}if(action==='clear')view.clear();complete();await pending;assert.equal(view.nodes['#analysis-result'].hidden,true);assert.doesNotMatch(view.nodes['#analysis-status'].textContent,/执行完成/);ready(view);}
});
test('分析进行中重复点击、校验和生成不产生额外请求',async()=>{
  let complete;const view=await analysisView((url,options,payload)=>new Promise(resolve=>{complete=()=>resolve(ok(reportFixture(payload.draft)));}));await view.validate();view.consent();const pending=view.analyse();await view.analyse();await view.validate();await view.format();assert.equal(view.requests.length,3);complete();await pending;ready(view);
});
for(const phase of ['fetch','json'])test(`本机分析 ${phase} 超时恢复按钮且没有模型费用提示`,async()=>{
  const view=await analysisView((url,options)=>{const waiting=new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('private-content'))));return phase==='fetch'?waiting:{ok:true,json:()=>waiting};});await view.validate();view.consent();const pending=view.analyse();await flushPromises();view.expire();await pending;assert.match(view.nodes['#analysis-status'].textContent,/15 秒.*没有新增模型费用/);assert.equal(view.nodes['#analysis-result'].hidden,true);assert.equal(view.nodes['#analyse-json'].disabled,false);ready(view);
});
test('错位快照、伪已匹配、篡改关联和事实、保存及模型标记均不能展示为完成',async()=>{
  const changes=[data=>data.report.case.notice='不同资料',data=>data.report.matches[0].status='matched',data=>data.report.matches[0].related_evidence_ids=[],data=>data.report.trusted_facts[0].verified_evidence_ids=['ev_001'],data=>data.report.trusted_facts[0].origin='model',data=>data.report.matches.reverse(),data=>data.report.trusted_facts.pop(),data=>data.saved=true,data=>data.report.model_generated=true,data=>data.report.verification.passed=true,data=>data.path='private',data=>data.report.extra='private'];
  for(const mutate of changes){const view=await analysisView((url,options,payload)=>{const data=reportFixture(payload.draft);mutate(data);return ok(data);});await view.validate();view.consent();await view.analyse();assert.equal(view.nodes['#analysis-result'].hidden,true);assert.match(view.nodes['#analysis-status'].textContent,/失败|不一致/);ready(view);}
});
test('本机错误只用固定提示，失败后同草稿可重试，不再调用模型',async()=>{
  let calls=0;const view=await analysisView((url,options,payload)=>++calls===1?{ok:false,status:503,json:async()=>({detail:'private-path secret',error_code:'analysis'})}:ok(reportFixture(payload.draft)));await view.validate();view.consent();await view.analyse();assert.equal(view.nodes['#analysis-result'].hidden,true);assert.doesNotMatch(view.nodes['#analysis-status'].textContent,/private-path|secret|密钥/);await view.analyse();assert.equal(view.nodes['#analysis-result'].hidden,false);assert.equal(view.requests.filter(item=>item.url==='/imports/format-json').length,1);ready(view);
});
test('JSON 验证和分析使用相同原始文本，不替换空白或人工修正',async()=>{
  const view=await analysisView();const draft=completeFixture().draft;draft.job.title='人工修改后的虚构岗位';const raw='\n'+JSON.stringify(draft,null,4)+'\n';view.nodes['#json-draft'].value=raw;view.nodes['#json-draft'].input();await view.validate();view.consent();await view.analyse();assert.equal(view.requests[1].options.body,'{"draft":'+raw+'}');assert.equal(view.requests[2].options.body,'{"draft":'+raw+',"analysis_confirmed":true}');assert.match(view.nodes['#analysis-summary'].textContent,/人工修改后的虚构岗位/);
});
test('未关联证据、资格和可信事实可查看，HTML 指令只作为文本',async()=>{
  const view=await analysisView();const draft=completeFixture().draft;draft.candidate.evidence.push({evidence_id:'ev_other',skill_id:'sql',description:'<img src=x onerror=alert(1)>',source:'虚构',level:'learning',verified:false});draft.qualifications=[{qualification_id:'qual_001',required:'模拟学历要求',declared:'未核实',verification:'unverified',source:'虚构声明',note:'不判断资格'}];view.nodes['#json-draft'].value=JSON.stringify(draft);view.nodes['#json-draft'].input();await view.validate();view.consent();await view.analyse();assert.equal(view.nodes['#analysis-other'].children[0].children[1].textContent,'<img src=x onerror=alert(1)>');assert.match(view.nodes['#analysis-qualifications'].children[0].textContent,/待核实/);const card=view.nodes['#analysis-matches'].children[0];assert.match(card.children.at(-1).children[1].textContent,/"verified_evidence_ids": \[\]/);assert.doesNotMatch(page,/innerHTML/);
});

test('分析完成或重复确认文字校对时，前序提示不会否认已有结果',async()=>{
  const view=await analysisView();await view.validate();view.consent();await view.analyse();view.confirm();
  assert.equal(view.nodes['#analysis-result'].hidden,false);
  assert.match(view.nodes['#review'].textContent,/声明仍待核实.*对应步骤/);
  assert.match(view.nodes['#json-status'].textContent,/本步不保存或触发分析.*对应步骤/);
  for(const id of ['#review','#json-status'])assert.doesNotMatch(view.nodes[id].textContent,/未生成结构化证据或匹配结果|没有保存或分析/);
  assert.match(view.nodes['#analysis-status'].textContent,/执行完成/);
});

test('分析期间生成和校验明确禁用，成功、失败、超时及取消后均恢复',async()=>{
  for(const finish of ['success','error','timeout','revoke','edit','clear']){
    let complete;const view=await analysisView((url,options,payload)=>new Promise((resolve,reject)=>{
      complete=()=>resolve(finish==='error'?{ok:false,status:503,json:async()=>({error_code:'analysis'})}:ok(reportFixture(payload.draft)));
      if(finish==='timeout')options.signal.addEventListener('abort',()=>reject(new Error('timeout')));
    }));
    await view.validate();view.consent();const pending=view.analyse();
    assert.equal(view.nodes['#format-json'].disabled,true);assert.equal(view.nodes['#validate-json'].disabled,true);
    if(finish==='timeout')view.expire();
    else {if(finish==='revoke'){view.nodes['#analysis-consent'].checked=false;view.nodes['#analysis-consent'].change();}if(finish==='edit')view.nodes['#json-draft'].input();if(finish==='clear')view.clear();complete();}
    await pending;assert.equal(view.nodes['#format-json'].disabled,false);assert.equal(view.nodes['#validate-json'].disabled,false);ready(view);
  }
});

test('撤销并重新分析后，旧响应不能提前解锁新请求的按钮',async()=>{
  const completions=[];const view=await analysisView((url,options,payload)=>new Promise(resolve=>completions.push(()=>resolve(ok(reportFixture(payload.draft))))));
  await view.validate();view.consent();const old=view.analyse();view.nodes['#analysis-consent'].checked=false;view.nodes['#analysis-consent'].change();
  assert.equal(view.nodes['#format-json'].disabled,false);view.consent();const latest=view.analyse();completions[0]();await old;
  assert.equal(view.nodes['#analysis-result'].hidden,true);assert.equal(view.nodes['#format-json'].disabled,true);assert.equal(view.nodes['#validate-json'].disabled,true);
  completions[1]();await latest;assert.equal(view.nodes['#analysis-result'].hidden,false);assert.equal(view.nodes['#format-json'].disabled,false);assert.equal(view.nodes['#validate-json'].disabled,false);ready(view);
});

test('步骤引导覆盖完整复验、明确确认、分析、编辑失效和清空，不自动请求',async()=>{
  const view=await analysisView();assert.match(view.nodes['#workflow-step'].textContent,/4 ·.*仅校验/);assert.match(view.nodes['#analyse-help'].textContent,/须先完整复验/);
  await view.validate();assert.match(view.nodes['#workflow-step'].textContent,/5 ·.*勾选分析确认/);assert.match(view.nodes['#analyse-help'].textContent,/须先逐项复核/);
  view.consent();assert.match(view.nodes['#analyse-help'].textContent,/可点击分析.*不调用模型/);await view.analyse();assert.match(view.nodes['#workflow-step'].textContent,/分析结果已展示.*待核实/);
  view.nodes['#json-draft'].input();assert.match(view.nodes['#workflow-step'].textContent,/4 ·/);assert.match(view.nodes['#analyse-help'].textContent,/须先完整复验/);assert.equal(view.requests.length,3);
  view.clear();assert.match(view.nodes['#workflow-step'].textContent,/1 ·.*选择文件/);assert.match(view.nodes['#analyse-help'].textContent,/尚无 JSON 草稿/);assert.equal(view.requests.length,3);
  assert.match(page,/id="analyse-json"[^>]*aria-describedby="analyse-help"/);
});

test('模型关闭、文字未确认及外发未同意的原因分别显示',async()=>{
  const disabled=mount();assert.match(disabled.nodes['#format-help'].textContent,/服务未启用模型整理/);disabled.choose();await disabled.run();assert.match(disabled.nodes['#workflow-step'].textContent,/2 ·.*校对/);
  const view=await modelView();view.nodes['#format-mode'].value='model';view.nodes['#format-mode'].change();assert.match(view.nodes['#format-help'].textContent,/请先确认文字校对/);view.confirm();assert.match(view.nodes['#format-help'].textContent,/勾选外发同意/);view.nodes['#model-consent'].checked=true;view.nodes['#model-consent'].change();assert.match(view.nodes['#format-help'].textContent,/可点击生成.*费用/);assert.equal(view.nodes['#analysis-result'].hidden,true);
});

test('分析期间步骤和禁用原因明确，取消后晚响应不恢复旧引导',async()=>{
  let complete;const view=await analysisView((url,options,payload)=>new Promise(resolve=>{complete=()=>resolve(ok(reportFixture(payload.draft)));}));await view.validate();view.consent();const pending=view.analyse();assert.match(view.nodes['#workflow-step'].textContent,/5 ·.*正在本机分析/);assert.match(view.nodes['#validate-help'].textContent,/暂时禁用/);assert.match(view.nodes['#format-help'].textContent,/暂时禁用/);view.nodes['#json-draft'].input();complete();await pending;assert.match(view.nodes['#workflow-step'].textContent,/4 ·/);assert.doesNotMatch(view.nodes['#workflow-step'].textContent,/已展示|正在本机分析/);
});

test('中文层级、必需加分要求和优先级只展示，不更改可信事实',async()=>{
  const view=await analysisView();const draft=completeFixture().draft;draft.job.requirements[1].category='preferred';
  for(const [index,level] of ['learning','practice','project','production'].entries())draft.candidate.evidence.push({evidence_id:'extra_'+index,skill_id:'python',description:'虚构声明',source:'模拟',level,verified:false});
  view.nodes['#json-draft'].value=JSON.stringify(draft);view.nodes['#json-draft'].input();await view.validate();view.consent();await view.analyse();
  const cards=view.nodes['#analysis-matches'].children;assert.match(cards[0].children[2].textContent,/必需要求.*输入优先级 2.*不用于评分/);assert.match(cards[1].children[2].textContent,/加分要求.*输入优先级 1/);
  const text=JSON.stringify(cards);for(const label of ['学习（learning）','练习（practice）','项目（project）','生产实践（production）'])assert.ok(text.includes(label));assert.match(view.nodes['#analysis-counts'].textContent,/已匹配 0.*部分匹配 0.*待核实 1/);
  const fact=JSON.parse(cards[0].children.at(-1).children[1].textContent);assert.equal(fact.origin,'python_deterministic_match');assert.equal(fact.status,'unverified');assert.deepEqual(fact.verified_evidence_ids,[]);assert.equal(fact.unverified_evidence_ids.length,5);
});

test('本地字段错误展示固定路径与中文原因，编辑清除提示且不再次调用模型',async()=>{
  const errorBody={error_code:'json',detail:'private-content',field_errors:[{path:'job.requirements[1].priority',reason:'priority'},{path:'candidate.evidence[0].verified',reason:'false_only'}]};
  let fail=true;const view=await modelView(async(url,options)=>url==='/imports/format-json'?ok(completeFixture()):fail?{ok:false,status:422,json:async()=>errorBody}:ok(validationFixture(JSON.parse(options.body).draft)));view.enable();await view.format();await view.validate();
  assert.equal(view.nodes['#field-errors'].hidden,false);assert.match(view.nodes['#field-errors'].children[0].textContent,/job.requirements\[1\].priority.*整数 1、2 或 3/);assert.match(view.nodes['#field-errors'].children[1].textContent,/必须为 false/);assert.doesNotMatch(JSON.stringify(view.nodes['#field-errors']),/private-content/);assert.equal(view.nodes['#analysis-consent'].disabled,true);
  view.nodes['#json-draft'].input();assert.equal(view.nodes['#field-errors'].hidden,true);assert.equal(view.nodes['#field-errors'].children.length,0);fail=false;await view.validate();assert.equal(view.nodes['#analysis-consent'].disabled,false);assert.equal(view.nodes['#field-errors'].hidden,true);
});

test('未知路径、原因、额外内容、过量提示和隐私类别均不展示服务端字段内容',async()=>{
  const safe={path:'job.requirements[0].priority',reason:'priority'};
  const invalid=[{error_code:'privacy',field_errors:[safe]},{error_code:'input',field_errors:[safe]},
    {error_code:'json',field_errors:[{path:'unknown-private-field',reason:'priority'}]},
    {error_code:'json',field_errors:[{path:'job.requirements[40].priority',reason:'priority'}]},
    {error_code:'json',field_errors:[{...safe,reason:'private-reason'}]},
    {error_code:'json',field_errors:[{...safe,reason:['priority']}]},
    {error_code:'json',field_errors:[{...safe,reason:'__proto__'}]},
    {error_code:'json',field_errors:[{...safe,value:'private-value'}]},
    {error_code:'json',field_errors:Array(9).fill(safe)}];
  for(const body of invalid){const view=await modelView(async(url)=>url==='/imports/format-json'?ok(completeFixture()):{ok:false,status:422,json:async()=>body});view.enable();await view.format();await view.validate();assert.equal(view.nodes['#field-errors'].hidden,true);assert.equal(view.nodes['#field-errors'].children.length,0);assert.doesNotMatch(view.nodes['#json-status'].textContent,/private-|__proto__/);}
});

test('修改后晚返回的字段错误不能恢复旧提示或步骤',async()=>{
  let complete;const view=await modelView(async(url)=>url==='/imports/format-json'?ok(completeFixture()):new Promise(resolve=>{complete=()=>resolve({ok:false,status:422,json:async()=>({error_code:'json',field_errors:[{path:'job.requirements[0].priority',reason:'priority'}]})});}));view.enable();await view.format();const pending=view.validate();assert.match(view.nodes['#workflow-step'].textContent,/正在本地校验/);view.nodes['#json-draft'].input();complete();await pending;assert.equal(view.nodes['#field-errors'].hidden,true);assert.equal(view.nodes['#field-errors'].children.length,0);assert.match(view.nodes['#workflow-step'].textContent,/4 ·.*修正/);ready(view);
});

test('已有分析结果时，待再次生成确认优先显示，取消恢复且不新增请求',async()=>{
  const view=await analysisView();await view.validate();view.consent();await view.analyse();await view.format();
  assert.equal(view.nodes['#regenerate-warning'].hidden,false);assert.match(view.nodes['#workflow-step'].textContent,/3 ·.*等待再次生成/);assert.equal(view.requests.length,3);assert.equal(view.nodes['#analysis-result'].hidden,false);
  view.nodes['#regenerate-cancel'].click();assert.match(view.nodes['#workflow-step'].textContent,/5 ·.*分析结果已展示/);assert.equal(view.requests.length,3);assert.equal(view.nodes['#analysis-result'].hidden,false);ready(view);
});

async function navigationView(raw,path='job.requirements[1].priority',reason='priority'){
  let calls=0;
  const view=await modelView(async url=>{calls++;return url==='/imports/format-json'?ok(completeFixture()):{ok:false,status:422,json:async()=>({error_code:'json',field_errors:[{path,reason}]})};});
  view.enable();await view.format();const editor=view.nodes['#json-draft'];editor.value=raw;editor.input();await view.validate();
  view.locate=()=>view.nodes['#field-errors'].children[0].children[0].click();view.calls=()=>calls;return view;
}
test('点击重复名称字段定位第二项原值，不改 JSON、不新增请求',async()=>{
  const draft=completeFixture().draft;draft.job.requirements[1].priority=true;
  const raw=JSON.stringify(draft,null,2),view=await navigationView(raw),editor=view.nodes['#json-draft'];view.locate();
  assert.equal(editor.value.slice(editor.selectionStart,editor.selectionEnd),'true');assert.equal(editor.selectionStart,raw.indexOf('true'));
  assert.equal(editor.value,raw);assert.equal(editor.focused,true);assert.equal(editor.scrolled.block,'center');assert.equal(view.calls(),2);
  assert.match(view.nodes['#field-location-status'].textContent,/已选中对应值.*第 \d+ 行.*仅定位/);
});
test('转义字段名、字符串伪键、括号和 Unicode 不影响原始位置',async()=>{
  const draft=completeFixture().draft;draft.notice='虚构😀 {"priority":true} \\ 引号"';draft.job.requirements[1].priority=true;
  const raw=JSON.stringify(draft,null,2).replaceAll('"priority"','"prio\\u0072ity"').replaceAll('\n','\r\n');
  const view=await navigationView(raw),editor=view.nodes['#json-draft'];view.locate();
  assert.equal(editor.selectionStart,raw.lastIndexOf('true'));assert.equal(editor.value.slice(editor.selectionStart,editor.selectionEnd),'true');assert.equal(editor.value,raw);
  assert.doesNotMatch(view.nodes['#field-location-status'].textContent,/无法/);
});
test('压缩 JSON 的远端字段会横向滚动，空容器和根路径也能定位',async()=>{
  const draft=completeFixture().draft;draft.notice='虚构'.repeat(500);
  for(const [path,reason,value] of [['job.requirements[1].priority','priority','1'],['qualifications','list','[]'],['draft','object',JSON.stringify(draft)]]){
    const raw=JSON.stringify(draft),view=await navigationView(raw,path,reason),editor=view.nodes['#json-draft'];view.locate();
    assert.equal(editor.value.slice(editor.selectionStart,editor.selectionEnd),value);if(path!=='draft')assert.ok(editor.scrollLeft>0);
  }
});
test('缺失字段定位最近父级，null 或越界数组不猜测其他同名字段',async()=>{
  const draft=completeFixture().draft;delete draft.job.requirements[1].priority;
  for(const [path,value] of [['job.requirements[1].priority',draft.job.requirements[1]],['qualifications[3].required',[]]]){
    const view=await navigationView(JSON.stringify(draft),path,'fields'),editor=view.nodes['#json-draft'];view.locate();
    assert.deepEqual(JSON.parse(editor.value.slice(editor.selectionStart,editor.selectionEnd)),value);assert.match(view.nodes['#field-location-status'].textContent,/字段不存在.*父级/);
  }
  draft.job=null;const view=await navigationView(JSON.stringify(draft)),editor=view.nodes['#json-draft'];view.locate();assert.equal(editor.value.slice(editor.selectionStart,editor.selectionEnd),'null');
});
test('重复键、非有限数和超深 JSON 不执行含糊定位或回显内容',async()=>{
  const raw=JSON.stringify(completeFixture().draft);
  for(const invalid of [raw.replace('{','{"notice":"private-value",'),raw.replace('"priority":2','"priority":1e400'),raw.replace('"notice":"模型整理，待复核"','"notice":'+ '['.repeat(34)+'0'+']'.repeat(34))]){
    const view=await navigationView(invalid),editor=view.nodes['#json-draft'];view.locate();assert.equal(editor.selectionStart,undefined);
    assert.equal(editor.value,invalid);assert.match(view.nodes['#field-location-status'].textContent,/无法可靠定位/);assert.doesNotMatch(view.nodes['#field-location-status'].textContent,/private-value/);
  }
});
test('过长草稿保守拒绝定位，不影响既有错误提示与原文',async()=>{
  const draft=completeFixture().draft;draft.notice='x'.repeat(120001);const raw=JSON.stringify(draft),view=await navigationView(raw);view.locate();
  assert.equal(view.nodes['#json-draft'].selectionStart,undefined);assert.equal(view.nodes['#json-draft'].value,raw);assert.equal(view.nodes['#field-errors'].hidden,false);assert.match(view.nodes['#field-location-status'].textContent,/大小／嵌套限制/);
});
test('语法错误不产生定位按钮；旧提示不能定位已修改或已清空草稿',async()=>{
  for(const action of ['edit','clear','silent-edit']){
    const raw=JSON.stringify(completeFixture().draft),view=await navigationView(raw),button=view.nodes['#field-errors'].children[0].children[0];
    if(action==='clear')view.clear();else{view.nodes['#json-draft'].value=raw+' ';if(action==='edit')view.nodes['#json-draft'].input();}
    button.click();assert.equal(view.nodes['#json-draft'].selectionStart,undefined);assert.equal(view.nodes['#field-location-status'].textContent,'');assert.equal(view.calls(),2);
  }
  const view=await navigationView('{invalid');assert.equal(view.nodes['#field-errors'].hidden,true);assert.equal(view.calls(),1);
});
test('旧定位按钮在重新校验后失效，即使草稿完全相同',async()=>{
  const view=await navigationView(JSON.stringify(completeFixture().draft)),old=view.nodes['#field-errors'].children[0].children[0];await view.validate();old.click();
  assert.equal(view.nodes['#json-draft'].selectionStart,undefined);view.locate();assert.equal(view.nodes['#json-draft'].value.slice(view.nodes['#json-draft'].selectionStart,view.nodes['#json-draft'].selectionEnd),'1');assert.equal(view.calls(),3);
});
function filterView(view,state){view.nodes['#analysis-filter'].value=state;view.nodes['#analysis-filter'].change();}
test('结果筛选保留全量统计和每条可信事实，仅改变卡片可见性',async()=>{
  const view=await analysisView();await view.validate();view.consent();await view.analyse();
  const cards=view.nodes['#analysis-matches'].children,counts=view.nodes['#analysis-counts'].textContent,facts=cards.map(card=>card.children.at(-1).children[1].textContent);
  assert.equal(view.nodes['#analysis-filter'].disabled,false);assert.match(view.nodes['#filter-status'].textContent,/全量要求 2 项；当前显示 2 项/);
  for(const [state,hidden] of [['unverified',[false,true]],['missing',[true,false]],['all',[false,false]],['unexpected',[false,false]]]){
    filterView(view,state);assert.deepEqual(cards.map(card=>card.hidden),hidden);assert.equal(view.nodes['#analysis-counts'].textContent,counts);
    assert.deepEqual(cards.map(card=>card.children.at(-1).children[1].textContent),facts);assert.equal(view.requests.length,3);assert.equal(view.nodes['#filter-empty'].hidden,true);
  }
  assert.equal(view.nodes['#analysis-filter'].value,'all');
});
test('零筛选结果明确提示，不把显示数量当成全量或隐藏其他证据和资格',async()=>{
  const view=await analysisView();const draft=completeFixture().draft;draft.job.requirements.pop();draft.candidate.evidence.push({evidence_id:'ev_sql',skill_id:'sql',description:'虚构',source:'模拟',level:'learning',verified:false});draft.qualifications=[{qualification_id:'q_1',required:'虚构要求',declared:'待确认',source:'模拟',verification:'unverified',note:'不判断资格'}];
  view.nodes['#json-draft'].value=JSON.stringify(draft);view.nodes['#json-draft'].input();await view.validate();view.consent();await view.analyse();
  const other=JSON.stringify(view.nodes['#analysis-other']),qualifications=JSON.stringify(view.nodes['#analysis-qualifications']);filterView(view,'missing');
  assert.equal(view.nodes['#filter-empty'].hidden,false);assert.match(view.nodes['#filter-status'].textContent,/全量要求 1 项；当前显示 0 项（缺少证据）/);
  assert.match(view.nodes['#analysis-counts'].textContent,/待核实 1.*缺少证据 0/);assert.equal(JSON.stringify(view.nodes['#analysis-other']),other);assert.equal(JSON.stringify(view.nodes['#analysis-qualifications']),qualifications);
  filterView(view,'all');assert.equal(view.nodes['#filter-empty'].hidden,true);assert.equal(view.nodes['#analysis-matches'].children[0].hidden,false);
});
test('编辑、撤销、清空和重新校验使旧筛选失效，新报告恢复全部',async()=>{
  for(const action of ['edit','revoke','clear','validate']){
    const view=await analysisView();await view.validate();view.consent();await view.analyse();filterView(view,'missing');
    if(action==='edit')view.nodes['#json-draft'].input();if(action==='revoke'){view.nodes['#analysis-consent'].checked=false;view.nodes['#analysis-consent'].change();}if(action==='clear')view.clear();if(action==='validate')await view.validate();
    assert.equal(view.nodes['#analysis-filter'].disabled,true);assert.equal(view.nodes['#filter-status'].textContent,'');assert.equal(view.nodes['#filter-empty'].hidden,true);filterView(view,'missing');assert.equal(view.nodes['#filter-status'].textContent,'');
    if(action==='clear')continue;
    if(action!=='revoke')await view.validate();view.consent();await view.analyse();assert.equal(view.nodes['#analysis-filter'].value,'all');assert.match(view.nodes['#filter-status'].textContent,/当前显示 2 项/);assert.equal(view.nodes['#analysis-matches'].children.every(card=>!card.hidden),true);
  }
});
test('重复分析失败清除旧筛选统计，重试成功从全部展示',async()=>{
  let calls=0;const view=await analysisView((url,options,payload)=>++calls===2?{ok:false,status:503,json:async()=>({error_code:'analysis'})}:ok(reportFixture(payload.draft)));
  await view.validate();view.consent();await view.analyse();filterView(view,'missing');await view.analyse();
  assert.equal(view.nodes['#analysis-result'].hidden,true);assert.equal(view.nodes['#analysis-filter'].disabled,true);assert.equal(view.nodes['#filter-status'].textContent,'');
  await view.analyse();assert.equal(view.nodes['#analysis-filter'].value,'all');assert.match(view.nodes['#filter-status'].textContent,/当前显示 2 项/);assert.equal(view.requests.filter(item=>item.url==='/imports/format-json').length,1);
});

test('文字值及包含空对象的数组按原样选中，不执行字段内容',async()=>{
  const draft=completeFixture().draft;draft.job.title='虚构😀 "标题" [ ]';draft.qualifications=[{}];
  for(const [path,reason,value] of [['job.title','text',draft.job.title],['qualifications[0]','fields',{}]]){
    const raw=JSON.stringify(draft),view=await navigationView(raw,path,reason),editor=view.nodes['#json-draft'];view.locate();
    assert.deepEqual(JSON.parse(editor.value.slice(editor.selectionStart,editor.selectionEnd)),value);assert.equal(editor.value,raw);assert.equal(view.calls(),2);
  }
  const duplicated=JSON.stringify(draft).replace('"title":','"ti\\u0074le":"虚构重复", "title":');const view=await navigationView(duplicated,'job.title','text');view.locate();assert.match(view.nodes['#field-location-status'].textContent,/无法可靠定位/);
});
test('四十项长报告筛选数量与全量统计、证据关联均保持一致',async()=>{
  const view=await analysisView(),draft=completeFixture().draft;
  draft.job.requirements=Array.from({length:40},(_,index)=>({requirement_id:'req_'+index,skill_id:index%2?'git':'python',description:'虚构要求 '+index,category:'required',priority:2}));
  view.nodes['#json-draft'].value=JSON.stringify(draft);view.nodes['#json-draft'].input();await view.validate();view.consent();await view.analyse();
  const cards=view.nodes['#analysis-matches'].children,counts=view.nodes['#analysis-counts'].textContent;
  assert.match(counts,/待核实 20.*缺少证据 20/);assert.equal(cards.length,40);
  for(const state of ['unverified','missing']){filterView(view,state);assert.equal(cards.filter(card=>!card.hidden).length,20);assert.match(view.nodes['#filter-status'].textContent,/全量要求 40 项；当前显示 20 项/);assert.equal(view.nodes['#analysis-counts'].textContent,counts);}
  filterView(view,'all');assert.equal(cards.filter(card=>!card.hidden).length,40);assert.equal(view.requests.length,3);
});
