// 使用 Node.js 内置测试工具执行页面脚本；替身仅模拟 DOM、网络与时钟。
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const page = fs.readFileSync(path.join(__dirname, 'demo.html'), 'utf8');
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
const example = JSON.parse(fs.readFileSync(path.join(
  __dirname, 'examples', 'careeragent_v1_3_api_analysis_output.json'
), 'utf8'));

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

function mount(fetch) {
  const nodes = Object.fromEntries([
    '#run', '#status', '#result', '#job-title', '#counts', '#matches', '#facts'
  ].map(id => [id, element()]));
  nodes['#run'].textContent = '运行脱敏分析';
  const timers = new Map();
  const delays = [];
  let nextTimer = 0;
  vm.runInNewContext(script, {
    document: {querySelector: id => nodes[id], createElement: element},
    fetch, AbortController,
    setTimeout(callback, delay) {
      delays.push(delay);
      timers.set(++nextTimer, callback);
      return nextTimer;
    },
    clearTimeout(id) { timers.delete(id); },
  });
  return {
    nodes, timers, delays,
    run: () => nodes['#run'].click(),
    expire() {
      assert.equal(timers.size, 1, '运行中的请求必须有超时限制');
      [...timers.values()][0]();
    },
  };
}

function success(data = example) {
  return {ok: true, status: 200, json: async () => data};
}

function assertReady(view) {
  assert.equal(view.nodes['#run'].disabled, false);
  assert.equal(view.nodes['#run'].textContent, '运行脱敏分析');
  assert.equal(view.nodes['#result'].attributes['aria-busy'], 'false');
  assert.equal(view.timers.size, 0, '请求结束后必须清除计时器');
}

test('固定请求展示原 API 的三项匹配与可信事实', async () => {
  let request;
  const view = mount(async (url, options) => {
    request = {url, options};
    return success();
  });
  await view.run();
  assert.equal(request.url, '/analyses');
  assert.deepEqual(JSON.parse(request.options.body), {
    username: 'test_user', job_id: 'demo_ai_agent_intern'
  });
  assert.equal(request.options.method, 'POST');
  assert.equal(view.nodes['#result'].hidden, false);
  assert.equal(view.nodes['#matches'].children.length, 3);
  assert.equal(view.nodes['#facts'].children.length, 3);
  assert.match(view.nodes['#counts'].children[0].textContent, /已匹配 2/);
  assert.match(view.nodes['#counts'].children[2].textContent, /待核实 1/);
  assertReady(view);
});

for (const [status, message] of [
  [404, /脱敏示例不存在/], [422, /演示请求未通过校验/],
  [503, /脱敏数据暂不可用/], [500, /本机服务暂时异常/]
]) {
  test(`HTTP ${status} 显示固定提示且允许重试`, async () => {
    const view = mount(async () => ({
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
  const view = mount(async () => { throw new Error('private-path'); });
  await view.run();
  assert.match(view.nodes['#status'].textContent, /无法连接本机服务/);
  assert.doesNotMatch(view.nodes['#status'].textContent, /private-path/);
  assertReady(view);
});

for (const phase of ['fetch', 'json']) {
  test(`${phase} 阶段超时中止请求、恢复按钮并支持再次成功`, async () => {
    let attempt = 0;
    let signal;
    const view = mount(async (_, options) => {
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
  const view = mount(async () => success({}));
  await view.run();
  assert.match(view.nodes['#status'].textContent, /结果格式异常/);
  assert.equal(view.nodes['#result'].hidden, true);
  assertReady(view);
});

test('无法解析 JSON 时不展示原始响应内容', async () => {
  const view = mount(async () => ({ok: true, json: async () => {
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
  const view = mount(() => {
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
  const view = mount(async () => ++attempt === 2
    ? {ok: false, status: 503} : success());
  await view.run();
  await view.run();
  assert.equal(view.nodes['#result'].hidden, true);
  await view.run();
  assert.equal(view.nodes['#result'].hidden, false);
  assert.equal(view.nodes['#matches'].children.length, 3);
  assert.equal(view.nodes['#facts'].children.length, 3);
  assertReady(view);
});

test('要求中的 HTML 字样只作为文字呈现', async () => {
  const data = structuredClone(example);
  data.matches[0].description = '<img src=x onerror=alert(1)>';
  const view = mount(async () => success(data));
  await view.run();
  const heading = view.nodes['#matches'].children[0].children[1];
  assert.equal(heading.textContent, data.matches[0].description);
  assert.equal(heading.children.length, 0);
  assertReady(view);
});
