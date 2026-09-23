# CareerAgent

CareerAgent 是一个面向求职学习场景的 Python Agent 项目。它使用受控工具读取脱敏岗位、候选人证据和学习进度，由 Python 计算并核对匹配结果，再让千问生成明确标为未验证内容的结构化建议。

最新版本：`V1.4`

## 文档导航

- 当前功能与验证结果：[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
- 当前公开版本范围：[`docs/PROJECT_SCOPE.md`](docs/PROJECT_SCOPE.md)
- 版本演进与历史验证证据：[`docs/CAREER_AGENT_HISTORY.md`](docs/CAREER_AGENT_HISTORY.md)
- 项目主张、代码证据与面试讲解：[`docs/PROJECT_EVIDENCE.md`](docs/PROJECT_EVIDENCE.md)

## 当前功能

- 对用户、学习进度、脱敏岗位和候选人证据进行结构与范围校验；复习任务由本地可信目录核对题号、题名和专题。
- 千问通过受控工具读取当前范围内的数据并生成结构化建议；Python 核对来源，模型文字仍标为未验证。普通建议流程也可使用无 API 费用的本地规则模式。
- 用户明确选择更新后，模型只提出参数；Python 展示并校验提案，只有用户输入精确的 `CONFIRM` 才写入和回读。
- Python 按相同 `skill_id`、证据层级和验证标记计算 `matched`、`partial`、`unverified`、`missing`；`trusted_facts` 只由结构化数据生成。
- 本地 FastAPI 提供健康检查、岗位要求查询和默认离线确定性分析；HTTP 客户端不能指定数据文件或模型，分析不需要密钥。
- 固定脱敏案例与模型响应替身用于离线评估，报告公开适用案例数和指标局限；V1.4 补充项目主张与代码、测试、演示的证据映射。

普通建议循环只向模型开放 `get_study_progress`。写入提案必须由用户明确选择 `update` 才会生成，确认前不会修改文件。

复习任务结构、建议来源及各版本的实现细节见[项目状态](docs/PROJECT_STATUS.md)与[版本历史](docs/CAREER_AGENT_HISTORY.md)。

## 环境

- Python 3.13
- Windows / PowerShell
- 千问 AI 平台 OpenAI 兼容接口
- FastAPI 与 Uvicorn 本地只读 API

## 安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果只体验 V1.3 本地只读 API，可以跳过下面的 `.env` 和千问密钥配置，直接进入“本地只读 API”章节。

复制 `.env.example` 为 `.env`，然后只在本地填写：

```ini
DASHSCOPE_API_KEY=你的千问API密钥
CAREER_AGENT_MODE=llm
```

`.env` 已被 `.gitignore` 忽略。请勿把真实密钥写入代码、截图或提交记录。

## 命令行运行

```powershell
.venv\Scripts\python.exe main.py
```

按提示输入演示用户名：

```text
test_user
```

随后选择操作：

```text
advice  # 生成建议；直接回车也是此模式
job     # 分析脱敏岗位与候选人证据
update  # 根据明确要求生成更新提案
```

选择 `job` 后输入脱敏示例岗位 ID：

```text
demo_ai_agent_intern
```

岗位分析会产生千问 API Token 用量，但只允许读取固定的项目数据文件，不会执行写入。

选择 `update` 后，程序会先显示完整提案。核对用户名、字段和新值后：

```text
CONFIRM  # 精确输入此确认词才会保存
其他输入  # 取消，不调用写入工具
```

如需使用完全本地、无 API 费用的规则模式，将 `.env` 中的模式改为：

```ini
CAREER_AGENT_MODE=rule
```

## 本地只读 API

V1.3 API 默认读取仓库内的脱敏示例数据，离线分析不调用真实模型，不需要 API Key，也不会写入项目文件。服务仅供本机脱敏演示使用，请只按示例监听 `127.0.0.1`；当前没有身份验证，请勿用于真实候选人数据或公网部署。

在第一个 PowerShell 终端启动仅监听本机的服务：

```powershell
.venv\Scripts\python.exe -m uvicorn api_app:app --host 127.0.0.1 --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 后，在第二个 PowerShell 终端运行：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/demo_ai_agent_intern/requirements"

$analysisBody = @{
    username = "test_user"
    job_id = "demo_ai_agent_intern"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/analyses" `
    -Method Post `
    -ContentType "application/json" `
    -Body $analysisBody
```

分析结果中的三个状态应依次为 `matched`、`matched`、`unverified`。完整脱敏响应见 [`examples/careeragent_v1_3_api_analysis_output.json`](examples/careeragent_v1_3_api_analysis_output.json)。验证完成后在第一个终端按 `Ctrl+C` 停止服务。

## 测试

```powershell
.venv\Scripts\python.exe -m unittest -v
```

单元测试使用模型响应替身，不会真实调用千问，也不会产生模型费用。

运行 V1.2 脱敏离线评估集：

```powershell
.venv\Scripts\python.exe job_analysis_evaluation_runner.py
```

只运行一个案例、一个类别，或将报告保存为新文件：

```powershell
.venv\Scripts\python.exe job_analysis_evaluation_runner.py --case-id normal_project_data
.venv\Scripts\python.exe job_analysis_evaluation_runner.py --category security
.venv\Scripts\python.exe job_analysis_evaluation_runner.py --output "$env:TEMP\careeragent-v1-2-evaluation.json"
```

`--output` 仅接受 `.json` 路径，目标目录必须已存在，且不会覆盖已有文件或项目数据。保存前会扫描报告中的常见手机号、邮箱、绝对本地路径和密钥／令牌格式；这是有限的格式检查，不能保证发现所有敏感信息。

评估运行器只把固定夹具复制到临时目录，并调用现有受控工具和 JD Agent；不会修改项目数据，也不会调用真实千问。

V1.4 的完整离线测试为 168 项。26 个固定案例的观察结果与预设一致；4 个适用自由文本案例中有 3 个虚构声明被接受，而这些已知声明进入 `trusted_facts` 的数量为 0/4。这只说明固定案例中的事实字段隔离情况，**不代表真实模型面对任意 JD 的准确率或已消除幻觉**。

V1.4 的全新 Python 3.13.5 环境复现、本机 HTTP 验收、脱敏示例一致性与 17 份受版本控制 JSON 不变性记录见[项目状态](docs/PROJECT_STATUS.md)和[版本历史](docs/CAREER_AGENT_HISTORY.md)；个人贡献仍需按真实参与过程核对。固定案例的完整计数和局限见[离线评估报告](examples/careeragent_v1_2_evaluation_report.json)。

脱敏运行证据：

- [`examples/careeragent_v0_6_review_topics_output.json`](examples/careeragent_v0_6_review_topics_output.json)：只读工具与结构化建议。
- [`examples/careeragent_v0_7_confirmed_update_output.json`](examples/careeragent_v0_7_confirmed_update_output.json)：模型提案、用户确认与写入成功；其中复习任务保留当时的 V0.7 历史结构。
- [`examples/careeragent_v0_9b_job_match_output.json`](examples/careeragent_v0_9b_job_match_output.json)：两个岗位/证据只读工具与 Python 确定性匹配结果；不调用真实模型。
- [`examples/careeragent_v1_0_job_analysis_output.json`](examples/careeragent_v1_0_job_analysis_output.json)：三个只读工具、Python 权威匹配和结构化岗位分析；明确标注为离线模型替身示例。
- [`examples/careeragent_v1_2_evaluation_report.json`](examples/careeragent_v1_2_evaluation_report.json)：26 个固定案例的脱敏离线报告，包含案例分类、完整计数指标、复现命令和局限说明。
- [`examples/careeragent_v1_3_api_analysis_output.json`](examples/careeragent_v1_3_api_analysis_output.json)：本地 API 默认离线分析的完整脱敏响应，与自动化测试实际结果逐字段核对。

受控写入脱敏演示截图（离线测试数据与模型响应替身，不调用真实 API，也不修改真实学习数据）：

![CareerAgent V0.8 脱敏受控写入：参数提案、Python 参数预览、用户确认、工具成功与执行完成](docs/images/careeragent-v0-8-sanitized-confirmed-update.png)

## 数据流

```text
启动 main.py
→ 加载并验证用户
→ 选择 advice、job 或 update
├─ advice：千问调用只读工具 → 生成建议和sources → Python核对来源
├─ job：千问调用三个只读工具 → Python计算匹配与可信事实 → 模型生成未验证解释 → Python核对状态和来源
├─ update：千问生成参数提案 → Python验证 → 用户确认 → 执行或取消
├─ evaluation：加载脱敏案例和夹具 → 临时数据 → 模型替身运行Agent → 汇总指标
└─ local API：固定服务端文件 → Python确定性匹配 → trusted_facts → 只读HTTP响应
```

## 项目边界

- 建议流程中，千问可以选择只读工具；写入流程仍由程序和用户共同控制。
- `requested_tools` 表示模型提出调用，`used_tools` 表示 Python 已实际执行；取消时后者为空，确认执行后才包含写入工具。
- 当前没有 RAG、多 Agent、网页前端、自动岗位搜索或自动投递。
- `used_tools` 记录实际执行过的工具；`trace` 同时记录模型决策和程序动作。
- V1.3 API 只提供本地脱敏数据的只读访问和确定性分析，不包含身份系统、云部署或真实候选人数据。
- V1.2 安全与评估结果来自固定脱敏数据和模型替身，不冒充真实模型红队测试结论；`0/4` 可信事实泄漏也不等于完整幻觉治理。
