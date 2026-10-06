// 使用 Node.js 内置测试工具执行页面脚本；替身仅模拟 DOM、网络与时钟。
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

const page = fs.readFileSync(path.join(__dirname, 'demo.html'), 'utf8');
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
const python = process.platform === 'win32'
  ? path.join(__dirname, '.venv', 'Scripts', 'python.exe')
  : path.join(__dirname, '.venv', 'bin', 'python');
// 页面测试复用后端输出形状；后端预期与规则另由 Python 反例测试核对。
const reports = JSON.parse(execFileSync(python, ['-X', 'utf8', '-c',
  'import json; from demo_cases import list_demo_cases, run_demo_case; print(json.dumps([run_demo_case(c["case_id"]) for c in list_demo_cases()]))'
], {cwd: __dirname, encoding: 'utf8'}));
const catalogue = reports.map(report => report.case);
const profile = JSON.parse(execFileSync(python, ['-X', 'utf8', '-c',
  'import json; from fastapi.testclient import TestClient; from api_app import app; print(json.dumps(TestClient(app).get("/demo/profile").json()))'
], {cwd: __dirname, encoding: 'utf8'}));

function element() {
  return {
    children: [], attributes: {}, textContent: '', hidden: true, disabled: false,
    append(node) { this.children.push(node); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(name, handler) { this[name] = handler; },
  };
}

async function mount(fetch, loadFetch, profileFetch) {
  const nodes = Object.fromEntries([
    '#run', '#status', '#result', '#job-title', '#counts', '#matches', '#facts',
    '#case-select', '#inputs', '#expected', '#run-outcome', '#execution',
    '#verification', '#comparison', '#steps', '#show-profile', '#show-cases',
    '#case-view', '#profile-view', '#profile-content', '#profile-status',
    '#profile-retry', '#profile-basic', '#profile-groups', '#profile-learning', '#profile-tasks'
  ].map(id => [id, element()]));
  nodes['#run'].textContent = '运行并核对案例';
  const timers = new Map();
  const delays = [];
  let nextTimer = 0;
  const ready = vm.runInNewContext(script + '; loadPromise;', {
    document: {querySelector: id => nodes[id], createElement: element},
    fetch: (url, options) => url === '/demo/cases'
      ? (loadFetch ? loadFetch(url, options) : success(structuredClone(catalogue)))
      : url === '/demo/profile'
        ? (profileFetch ? profileFetch(url, options) : success(structuredClone(profile)))
        : fetch(url, options),
    AbortController,
    setTimeout(callback, delay) {
      delays.push(delay);
      timers.set(++nextTimer, callback);
      return nextTimer;
    },
    clearTimeout(id) { timers.delete(id); },
  });
  await ready;
  delays.length = 0;
  return {
    nodes, timers, delays,
    run: () => nodes['#run'].click(),
    showProfile: () => nodes['#show-profile'].click(),
    showCases: () => nodes['#show-cases'].click(),
    retryProfile: () => nodes['#profile-retry'].click(),
    select(caseId) {
      nodes['#case-select'].value = caseId;
      nodes['#case-select'].change();
    },
    expire() {
      assert.equal(timers.size, 1, '运行中的请求必须有超时限制');
      [...timers.values()][0]();
    },
  };
}

function success(data = structuredClone(reports[0])) {
  return {ok: true, status: 200, json: async () => data};
}

function assertReady(view) {
  assert.equal(view.nodes['#run'].disabled, false);
  assert.equal(view.nodes['#run'].textContent, '运行并核对案例');
  assert.equal(view.nodes['#case-select'].disabled, false);
  assert.equal(view.nodes['#result'].attributes['aria-busy'], 'false');
  assert.equal(view.timers.size, 0, '请求结束后必须清除计时器');
}

test('加载输入与预设后，通过案例 ID 运行真实匹配', async () => {
  let request;
  const view = await mount(async (url, options) => {
    request = {url, options};
    return success();
  });
  await view.run();
  assert.equal(request.url, '/demo/analyses');
  assert.deepEqual(JSON.parse(request.options.body), {
    case_id: 'verified_project'
  });
  assert.equal(request.options.method, 'POST');
  assert.equal(view.nodes['#result'].hidden, false);
  assert.equal(view.nodes['#matches'].children.length, 1);
  assert.equal(view.nodes['#facts'].children.length, 1);
  assert.match(view.nodes['#counts'].children[0].textContent, /已匹配 1/);
  assert.match(view.nodes['#verification'].textContent, /核对：通过/);
  assert.match(view.nodes['#execution'].textContent, /执行：完成/);
  assert.equal(view.nodes['#inputs'].children.length, 2);
  assert.match(view.nodes['#matches'].children[0].children.at(-1).textContent, /项目或生产级/);
  assertReady(view);
});

for (const [status, message] of [
  [404, /脱敏示例不存在/], [422, /演示请求未通过校验/],
  [503, /脱敏数据暂不可用/], [500, /本机服务暂时异常/]
]) {
  test(`HTTP ${status} 显示固定提示且允许重试`, async () => {
    const view = await mount(async () => ({
      ok: false, status,
      json() { throw new Error('错误响应不应直接展示'); },
    }));
    await view.run();
    assert.match(view.nodes['#status'].textContent, message);
    assert.equal(view.nodes['#result'].hidden, true);
    assertReady(view);
  });
}

test('连接中断时提示重启本机服务，不回显异常内容', async () => {
  const view = await mount(async () => { throw new Error('private-path'); });
  await view.run();
  assert.match(view.nodes['#status'].textContent, /无法连接本机服务/);
  assert.doesNotMatch(view.nodes['#status'].textContent, /private-path/);
  assertReady(view);
});

for (const phase of ['fetch', 'json']) {
  test(`${phase} 阶段超时中止请求、恢复按钮并支持再次成功`, async () => {
    let attempt = 0;
    let signal;
    const view = await mount(async (_, options) => {
      if (++attempt > 1) return success();
      signal = options.signal;
      const waiting = new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')));
      });
      return phase === 'fetch' ? waiting : {ok: true, json: () => waiting};
    });
    const pending = view.run();
    await Promise.resolve();
    assert.equal(view.nodes['#run'].disabled, true);
    assert.equal(view.nodes['#result'].attributes['aria-busy'], 'true');
    view.expire();
    await pending;
    assert.equal(signal.aborted, true);
    assert.deepEqual(view.delays, [10000]);
    assert.match(view.nodes['#status'].textContent, /10 秒/);
    assert.equal(view.nodes['#result'].hidden, true);
    assertReady(view);
    await view.run();
    assert.equal(view.nodes['#result'].hidden, false);
    assertReady(view);
  });
}

test('结果格式异常时隐藏结果并允许重试', async () => {
  const view = await mount(async () => success({}));
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#result'].hidden, true);
  assertReady(view);
});

test('无法解析 JSON 时不展示原始响应内容', async () => {
  const view = await mount(async () => ({ok: true, json: async () => {
    throw new Error('private-response');
  }}));
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.doesNotMatch(view.nodes['#status'].textContent, /private-response/);
  assert.equal(view.nodes['#result'].hidden, true);
  assertReady(view);
});

test('等待期间重复点击不产生第二次请求', async () => {
  let calls = 0;
  let complete;
  const view = await mount(() => {
    calls++;
    return new Promise(resolve => { complete = resolve; });
  });
  const pending = view.run();
  await view.run();
  assert.equal(calls, 1);
  complete(success());
  await pending;
  assertReady(view);
});

test('重新分析失败时不展示上一次成功结果，恢复后不累积卡片', async () => {
  let attempt = 0;
  const view = await mount(async () => ++attempt === 2
    ? {ok: false, status: 503} : success());
  await view.run();
  await view.run();
  assert.equal(view.nodes['#result'].hidden, true);
  await view.run();
  assert.equal(view.nodes['#result'].hidden, false);
  assert.equal(view.nodes['#matches'].children.length, 1);
  assert.equal(view.nodes['#facts'].children.length, 1);
  assertReady(view);
});

test('要求中的 HTML 字样只作为文字呈现', async () => {
  const data = structuredClone(reports[0]);
  data.analysis.matches[0].description = '<img src=x onerror=alert(1)>';
  data.verification.passed = false;
  const view = await mount(async () => success(data));
  await view.run();
  const heading = view.nodes['#matches'].children[0].children[1];
  assert.equal(heading.textContent, data.analysis.matches[0].description);
  assert.equal(heading.children.length, 0);
  assertReady(view);
});

for (const [caseId, state] of [
  ['verified_practice', 'partial'], ['unverified_claim', 'unverified'],
  ['no_evidence', 'missing']
]) {
  test(`切换 ${caseId} 后，输入、实际状态与核对结果同步变化`, async () => {
    const report = structuredClone(reports.find(item => item.case.case_id === caseId));
    let requested;
    const view = await mount(async (_, options) => {
      requested = JSON.parse(options.body).case_id;
      return success(report);
    });
    view.select(caseId);
    assert.equal(view.nodes['#result'].hidden, true);
    await view.run();
    assert.equal(requested, caseId);
    assert.equal(view.nodes['#matches'].children[0].className, `match ${state}`);
    assert.match(view.nodes['#execution'].textContent, /执行：完成/);
    assert.match(view.nodes['#verification'].textContent, /核对：通过/);
    assertReady(view);
  });
}

test('非法证据显示输入被拒绝，但案例核对通过且无匹配结果', async () => {
  const report = structuredClone(reports.find(item => item.case.case_id === 'invalid_evidence'));
  const view = await mount(async () => success(report));
  view.select('invalid_evidence');
  await view.run();
  assert.match(view.nodes['#execution'].textContent, /输入被拒绝/);
  assert.match(view.nodes['#verification'].textContent, /核对：通过/);
  assert.equal(view.nodes['#result'].hidden, true);
  assert.equal(view.nodes['#run-outcome'].hidden, false);
  assert.equal(view.nodes['#steps'].children.length, 3);
  assertReady(view);
});

test('实际结果偏离预设时，不能显示核对通过', async () => {
  const report = structuredClone(reports[0]);
  report.verification.passed = false;
  const view = await mount(async () => success(report));
  await view.run();
  assert.match(view.nodes['#verification'].textContent, /核对：未通过/);
  assert.equal(view.nodes['#verification'].className, 'outcome fail');
  assert.equal(view.nodes['#result'].hidden, false);
});

test('案例响应串台时拒绝显示结果', async () => {
  const view = await mount(async () => success(reports[1]));
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#result'].hidden, true);
  assert.match(view.nodes['#verification'].textContent, /未完成/);
});

test('案例加载失败后可以重试加载，再运行分析', async () => {
  let loads = 0;
  const view = await mount(async () => success(), async () => ++loads === 1
    ? {ok: false, status: 503} : success(structuredClone(catalogue)));
  assert.equal(view.nodes['#run'].textContent, '重新加载案例');
  assert.equal(view.nodes['#case-select'].disabled, true);
  await view.run();
  assert.equal(view.nodes['#case-select'].disabled, false);
  await view.run();
  assert.match(view.nodes['#verification'].textContent, /核对：通过/);
  assertReady(view);
});

test('案例目录格式异常时不回显异常信息，允许重新加载', async () => {
  const view = await mount(async () => success(), async () => success([
    {data_kind: 'synthetic_demo'}
  ]));
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#run'].textContent, '重新加载案例');
  assert.equal(view.nodes['#case-select'].disabled, true);
});

test('完整历史资料显示全部证据、学习记录和复习任务', async () => {
  const view = await mount(async () => success());
  await view.showProfile();
  assert.equal(view.nodes['#case-view'].hidden, true);
  assert.equal(view.nodes['#profile-view'].hidden, false);
  assert.equal(view.nodes['#profile-content'].hidden, false);
  assert.match(view.nodes['#profile-basic'].children[0].textContent, /test_user.*AI Agent开发/);
  const groups = view.nodes['#profile-groups'].children;
  assert.match(groups[0].children[0].textContent, /2 条/);
  assert.match(groups[1].children[0].textContent, /0 条/);
  assert.match(groups[2].children[0].textContent, /1 条/);
  assert.equal(view.nodes['#profile-learning'].children.length, 6);
  assert.match(view.nodes['#profile-learning'].children[5].textContent, /106/);
  assert.equal(view.nodes['#profile-tasks'].children.length, 2);
  assert.match(view.nodes['#profile-tasks'].children[0].children[0].textContent, /560/);
});

test('历史资料与模拟分析分开展示，切回后仍可运行案例', async () => {
  const view = await mount(async () => success());
  await view.showProfile();
  view.showCases();
  assert.equal(view.nodes['#profile-view'].hidden, true);
  assert.equal(view.nodes['#case-view'].hidden, false);
  await view.run();
  assert.match(view.nodes['#verification'].textContent, /核对：通过/);
});

test('读取资料失败后可重试，失败时不显示残留旧资料', async () => {
  let attempt = 0;
  const view = await mount(async () => success(), undefined, async () => ++attempt === 2
    ? {ok: false, status: 503} : success(structuredClone(profile)));
  await view.showProfile();
  await view.showProfile();
  assert.equal(view.nodes['#profile-content'].hidden, true);
  assert.equal(view.nodes['#profile-retry'].hidden, false);
  await view.retryProfile();
  assert.equal(view.nodes['#profile-content'].hidden, false);
  assert.equal(view.nodes['#profile-retry'].hidden, true);
});

test('资料返回其他用户时不能显示完整资料', async () => {
  const wrong = structuredClone(profile);
  wrong.username = 'other_user';
  const view = await mount(async () => success(), undefined, async () => success(wrong));
  await view.showProfile();
  assert.equal(view.nodes['#profile-content'].hidden, true);
  assert.match(view.nodes['#profile-status'].textContent, /资料格式异常/);
});

test('目录中后续案例异常时整组拒绝，允许重新加载', async () => {
  const broken = structuredClone(catalogue);
  broken[1].candidate = null;
  const view = await mount(async () => success(), async () => success(broken));
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#case-select'].disabled, true);
  assert.equal(view.nodes['#run'].textContent, '重新加载案例');
});

test('可信事实缺失但声称核对通过时不能展示成功', async () => {
  const report = structuredClone(reports[0]);
  report.analysis.trusted_facts = [];
  const view = await mount(async () => success(report));
  await view.run();
  assert.equal(view.nodes['#result'].hidden, true);
  assert.match(view.nodes['#verification'].textContent, /未完成/);
});

test('拒绝报告夹带分析结果时按格式错误处理', async () => {
  const report = structuredClone(reports.at(-1));
  report.analysis = structuredClone(reports[0].analysis);
  const view = await mount(async () => success(report));
  view.select('invalid_evidence');
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.match(view.nodes['#verification'].textContent, /未完成/);
});

test('报告不能替换运行前预设再声称核对通过', async () => {
  const report = structuredClone(reports[0]);
  report.case.expected.states[0].status = 'missing';
  const view = await mount(async () => success(report));
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#result'].hidden, true);
});

test('历史证据分组遗漏时不能声称完整资料', async () => {
  const wrong = structuredClone(profile);
  wrong.evidence_groups.verified_application = [];
  const view = await mount(async () => success(), undefined, async () => success(wrong));
  await view.showProfile();
  assert.equal(view.nodes['#profile-content'].hidden, true);
  assert.match(view.nodes['#profile-status'].textContent, /资料格式异常/);
});
