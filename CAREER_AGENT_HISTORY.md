# CareerAgent 开发历史

本文件按版本记录 CareerAgent 已经完成并有证据支持的开发过程。当前状态请查看 `PROJECT_STATUS.md`；历史条目中的“尚未完成”只表示当时版本的边界，不代表现在仍未完成。

## 2026-09-11：V0 最小闭环

完成流程：

```text
加载测试 JSON
→ 输入并清理用户名
→ 查找用户资料
→ 读取求职目标和学习进度
→ 根据 agent_progress 执行固定规则
→ 输出建议
```

主要成果：

- 建立不包含真实隐私的 `users.json` 演示数据。
- 使用 `json.load()` 将 JSON 文件转换成 Python 字典。
- 支持正常用户名、空用户名和不存在用户三条路径。
- 第一条建议会根据 `agent_progress` 是否包含“尚未完成”决定，而不是无条件输出。
- 正常路径实际运行成功。

当时边界：只有一条主要规则，还没有独立验证函数、工具、Agent Loop 或 LLM。

## 2026-09-12：规则扩展与资料验证

主要成果：

- 建议扩展为 Python、LeetCode、Agent 三类。
- 最终输出改为包含用户名、目标岗位和分类建议的结构化 JSON。
- 提取 `validate_user_profile(user_profile)`，只负责验证单个用户资料：
  - 是否为字典；
  - 必要字段是否存在；
  - 字段值是否为字符串。
- JSON 文件不存在、JSON 损坏和根结构错误会被清晰拦截。
- Agent 建议升级为包含 `task` 和 `reason` 的可解释结构。
- 建立 `PROJECT_SCOPE.md`，明确第一版包含与不包含的范围。

验证证据：

```text
Ran 8 tests
OK
```

当时边界：仍是规则程序，没有真实模型调用和 Python 工具调用循环。

## 2026-09-13：学习进度读取工具

新增：

```python
get_study_progress(username, progress_file)
```

主要成果：

- 用户基础资料与学习进度数据拆分为 `users.json` 和 `study_progress.json`。
- 工具复用已有 JSON 加载逻辑，按用户名返回可序列化字典。
- 返回 Python 进度、LeetCode 专题、Agent 进度和复习任务。
- 文件、JSON、用户和资料结构错误均返回明确的结构化结果。
- 工具函数只返回数据，不直接打印最终计划或生成建议。

独立工具阶段验证：13 项测试通过。

## 2026-09-13：V0.2 读取工具接入主流程

主要成果：

- `main.py` 不再直接从基础资料读取学习进度，而是调用 `get_study_progress()`。
- 工具结果参与三类建议生成。
- 最终输出新增 `used_tools: ["get_study_progress"]`。
- 滑动窗口专题能生成包含 `task` 和 `reason` 的建议。
- 保存脱敏输出 `examples/careeragent_v0_2_output.json`。

验证证据：

```text
Ran 14 tests
OK
```

当时边界：`used_tools` 只是规则程序的执行记录，尚不是 LLM 自主选择工具。

## 2026-09-13：V0.3 学习进度更新工具

新增：

```python
update_study_progress(username, field, new_value, progress_file)
```

主要成果：

- 只允许更新三个文本进度字段和 `review_tasks`。
- 更新前检查字段白名单、新值类型、用户名和原资料结构。
- 先写临时文件，再替换原 JSON，降低写入中断导致文件损坏的风险。
- 使用临时副本完成真实写入与重新加载验证，没有污染演示数据。

验证证据：

```text
Ran 18 tests
OK
```

当时边界：更新工具没有接入普通建议流程，避免无条件修改学习记录。

## 2026-09-13：V0.4 规则版受控循环

新增：

```python
run_agent_loop(username, progress_file, max_steps=3)
```

主要成果：

- 第一步读取学习进度，第二步根据规则生成建议并主动停止。
- 使用 `max_steps` 防止无限循环。
- 工具失败时立即停止。
- `trace` 记录每一步动作和状态。
- `stop_reason` 区分完成、工具错误和达到最大步数。
- 规则模式不会自动调用写入工具。
- 保存脱敏输出 `examples/careeragent_v0_4_loop_output.json`。

验证证据：

```text
Ran 21 tests
OK
```

当时边界：循环骨架已经存在，但规划步骤仍由 Python 规则决定，不属于 LLM 驱动的 Function Calling。

## 2026-09-13：V0.5 千问 Function Calling

V0.5 的学习成果归属 2026-09-13，代码与证据于次日完成整理。

主要成果：

- 接入千问 AI 平台 `qwen3.8-flash` 的 OpenAI 兼容接口。
- 新增 `qwen_agent.py`，把模型调用与 `main.py` 的本地数据逻辑分开。
- 第一轮由千问决定是否调用只读工具 `get_study_progress`。
- Python 控制层验证工具名称和当前用户名，并固定注入学习进度文件路径。
- 工具结果返回模型后，第二轮关闭工具列表并启用严格 JSON Schema。
- Python、LeetCode、Agent 三类建议统一包含 `task` 和 `reason`。
- 输出记录模型名称、Token 用量、实际工具、执行轨迹和停止原因。
- 原规则循环保留，可通过 `CAREER_AGENT_MODE=rule` 使用。
- `update_study_progress` 没有开放给模型自动调用。
- 新增 `README.md`、`requirements.txt`、`.env.example` 和脱敏运行示例。

调试记录：

- 第一次真实主流程中，模型成功请求读取工具，但最终 JSON 没有遵循约定结构。
- 原因是工具列表和结构化输出约束在两轮中同时持续开放。
- 修正为“第一轮工具决策、第二轮严格结构化输出”后，真实主流程通过。

验证证据：

```text
Ran 26 tests
OK
```

- 最小 API 连通性测试返回 `QWEN_API_OK`。
- 最终真实验收：`mode=llm_tool_calling`、`used_tools=["get_study_progress"]`、`stop_reason=completed`。
- 一次验收运行使用 885 Tokens。
- 用户随后在 PyCharm 中再次运行成功，使用 924 Tokens，退出码为 0。
- 脱敏结果保存在 `examples/careeragent_v0_5_qwen_output.json`。

## 2026-09-14：本地 Git 基线

- 在 `D:\Projects\agent_project` 初始化本地 Git 仓库，默认分支为 `main`。
- 使用个人全局 Git 身份创建首次提交：`ce8cba2 feat: add CareerAgent V0.5`。
- 首次提交包含 16 个公开项目文件；`.env`、虚拟环境、IDE 配置、私人学习记录和本地协作文档均由 `.gitignore` 排除。
- 提交前使用项目虚拟环境运行 26 项离线测试，结果为 `OK`。
- 当前尚未创建或连接 GitHub 等远程仓库，代码仍只保存在本地。

## 2026-09-14：V0.6 复习任务专题结构化

主要成果：

- `review_tasks` 从题号字符串列表改为包含 `problem_id`、`title`、`topic` 的字典列表。
- `get_study_progress` 会拒绝旧字符串结构、缺少字段、额外字段以及空白字段。
- `update_study_progress` 只允许写入完整且合法的复习任务字典列表。
- 返回给模型的数据只保留三个约定字段。
- 模型提示词明确区分当前主线专题与每道题自己的真实专题，并限制原因引用工具事实。
- 新增 5 项数据结构与更新测试。

验证证据：

```text
Ran 31 tests
OK
```

- 真实千问回归中，560 被正确识别为前缀和与哈希表，283 被正确识别为双指针。
- `mode=llm_tool_calling`、`stop_reason=completed`，本次使用 1032 Tokens。
- 脱敏输出保存在 `examples/careeragent_v0_6_review_topics_output.json`。

## 2026-09-14：V0.7 受控写入确认

主要成果：

- 主流程新增 `advice/update` 操作选择，直接回车仍进入只读建议流程。
- 只有用户明确选择 `update` 并输入更新要求后，千问才会生成写入参数提案。
- 写入提案通过固定的 `update_study_progress` 工具 Schema 约束。
- Python 再次验证当前用户名、字段白名单和值结构，不信任模型直接写入。
- 提案阶段用 `requested_tools` 记录模型请求，用空的 `used_tools` 明确表示工具尚未执行。
- 提案生成后先展示给用户，只有精确输入 `CONFIRM` 才会执行写入。
- 其他确认输入会以 `user_cancelled` 停止，且 `used_tools` 保持为空。
- 确认后执行 `update_study_progress`；写入成功或失败都会进入执行轨迹。

验证证据：

```text
Ran 41 tests
OK
```

- 真实千问提案运行成功，模型提出更新 `agent_progress`，本次使用 579 Tokens。
- 运行前后 `study_progress.json` 的 SHA-256 完全一致，确认提案阶段没有修改文件。
- 确认、取消和写入失败分支均通过离线测试；确认分支还在临时 JSON 上完成了真实保存与重新读取。
- 脱敏输出保存在 `examples/careeragent_v0_7_update_proposal_output.json`。
- 用户随后在真实主流程中检查提案并亲自输入 `CONFIRM`。
- 最终状态为 `completed`，`update_study_progress` 执行成功，本次使用 583 Tokens。
- 磁盘文件重新加载成功；`agent_progress` 更新，其他学习进度字段保持不变。
- 写入后 41 项测试再次通过；依赖演示数据旧值的测试已改用独立临时数据。
- 脱敏确认结果保存在 `examples/careeragent_v0_7_confirmed_update_output.json`。
- V0.7 已提交到本地 Git：`3ae063a feat: add CareerAgent V0.7 confirmed updates`。

当前边界：V0.7 受控写入、本地版本提交和 README 代表性运行截图均已完成。

## 2026-09-16：V0.8 本地事实校验与建议来源

主要成果：

- `review_tasks` 升级为整数题号、题名、专题列表和复习状态。
- 本地可信目录记录 560、283、76、438、239 的题名和真实专题。
- `get_study_progress` 在数据进入模型前校验题号、题名和专题映射。
- 模型建议 Schema 新增 `sources`，Python 会与工具读取结果精确核对。
- 模型替身把 560 错误关联为双指针时，结果以 `invalid_model_output` 被拒绝，模型调用次数保持两次，没有重试。
- `update_study_progress` 写入后在程序内部重新读取磁盘，回读不一致时返回失败。

验证证据：

```text
Ran 46 tests
OK
```

- 事实映射和错误来源验证均使用本地数据与模型替身，没有调用真实 API。
- 用户随后真实运行现有受控更新流程，使用 610 Tokens，并完成参数确认和磁盘写入；该运行没有验证新增建议 `sources` Schema。
- 随后单独授权的真实只读验收成功：`get_study_progress` 被实际调用，三类建议均带与工具结果一致的 `sources`，本地校验通过并以 `completed` 停止。
- 本次只读验收使用 1292 Tokens（输入 839、输出 453），没有执行写入工具。
- 用户提供了真实 PyCharm 运行截图，README 已展示参数提案、精确 `CONFIRM`、实际工具记录和完成状态；测试与安全检查结论不要求分别截图。

当前边界：V0.8 的离线测试、受控写入、建议 `sources` 真实千问验收和 README 展示证据均已完成；公开仓库 `https://github.com/evanMai1021/career-agent` 已创建并首次推送，远程 `main` 与本地提交一致。

## 2026-09-18：V0.8.1 非空白文本校验

主要成果：

- `target_role` 只有空白字符时，用户资料验证会拒绝继续运行。
- `get_study_progress` 会拒绝空白的 Python、LeetCode 或 Agent 文本进度，避免无有效内容的数据进入建议流程。
- `update_study_progress` 会在读写文件前拒绝空白文本值，避免确认流程把已有进度清空。
- 新增三项回归测试；空白写入测试同时验证临时学习进度文件未发生变化。

验证证据：

```text
Ran 49 tests in 0.056s
OK
```

- 完整测试使用项目 `.venv` 和模型响应替身，没有调用真实 API。
- 测试前后 `users.json` 与 `study_progress.json` 的 SHA-256 均保持不变。
- V0.8.1 的功能提交为 `f07940e fix: reject blank profile and progress text`。

## 2026-09-18：V0.9a 岗位与个人证据数据契约

主要成果：

- 新增脱敏 `jobs.json` 与 `candidate_evidence.json`。
- 新增 `job_data.py`，校验岗位、岗位要求、候选人证据和两份 JSON 根结构。
- 岗位要求类别限制为 `required` 或 `preferred`，优先级限制为整数 1、2、3，并拒绝布尔值。
- 证据层级限制为 `learning`、`practice`、`project` 或 `production`，`verified` 必须是布尔值。
- 校验重复岗位 ID、要求 ID、用户名和证据 ID，同时允许候选人的证据列表为空。
- 代码审阅发现非字符串 `category` 和 `level` 会触发 `TypeError`；新增两项回归测试后，改为先验证字符串类型再检查枚举值。

验证证据：

```text
Ran 17 tests in 0.004s
OK

Ran 66 tests in 0.062s
OK
```

- `job_data.py`、`test_job_data.py`、`main.py`、`test_main.py` 和 `qwen_agent.py` 语法检查通过。
- 完整测试前后四份项目 JSON 的 SHA-256 均保持不变。
- V0.9a 全程使用离线数据和模型替身，没有调用千问或产生 API 费用。
- 数据契约只能验证结构和记录的验证状态，不能自动证明证据描述在现实中真实。
- 本阶段不实现岗位匹配。功能提交为 `dc004f2 feat: add V0.9a job and evidence schema`。

## 2026-09-18：V0.9b 本地可解释 JD 匹配

主要成果：

- 固定 `matched`、`partial`、`unverified`、`missing` 的确定性判定矩阵。
- `match_job_requirements` 只比较完全相同的 `skill_id`，并按最高已验证层级确定状态。
- `verified=false` 的高层级描述不能提升匹配状态。
- 新增 `get_job_requirements` 和 `get_candidate_evidence` 两个受控只读工具。
- 工具复用 V0.9a 根结构校验，并为无效查询、文件错误、非法数据和未知目标返回结构化错误。
- 匹配结果保留原岗位要求、唯一状态和相关证据 ID，输出顺序与岗位要求一致。

验证证据：

```text
Ran 24 tests
OK

Ran 90 tests
OK
```

- 两个只读工具和匹配函数已使用项目脱敏数据实际运行，得到两个 `matched` 和一个 `unverified`；自动化测试会将实际结果与保存的脱敏示例精确比较。
- 脱敏输出保存在 `examples/careeragent_v0_9b_job_match_output.json`。
- Python 语法检查通过；测试前后四份项目 JSON 的 SHA-256 均保持不变。
- V0.9b 没有调用千问或产生 API 费用，两个新工具也尚未接入 `main.py` 或模型工具 Schema。
- 功能提交为 `8db6be3 feat: add V0.9b deterministic job matching`。

## 2026-09-18：V1.0 受控 JD 分析 Agent

主要成果：

- 新增 `job_analysis_agent.py`，受控调用岗位、候选人证据和学习进度三个只读工具。
- 文件路径只由 Python 控制层提供；模型不能指定任意本地路径。
- 模型请求和工具返回都会核对当前用户名与岗位 ID，阻止跨用户、跨岗位读取。
- `match_job_requirements` 继续负责确定匹配状态，模型只能生成解释、差距学习任务和面试问题。
- Python 会逐项核对 `requirement_id`、`status`、`related_evidence_ids` 和学习进度来源。
- `main.py` 新增 `job` 操作；规则模式不会调用岗位分析模型。

验证证据：

```text
Ran 106 tests in 0.138s
OK
```

- 14 项岗位分析与脱敏示例测试和 2 项主流程接入测试通过，Python 语法检查通过。
- 离线端到端测试使用真实项目脱敏数据和模型响应替身，得到两个 `matched` 和一个 `unverified`。
- 第一次真实千问验收成功调用三个只读工具，但最终输出因提示词与校验器的数量、顺序契约不一致而被拒绝，使用 3462 Tokens。
- 修复契约说明并增加具体校验错误后，完整离线回归通过；加入脱敏示例一致性检查后共 106 项测试通过。
- 第二次真实千问验收成功调用三个只读工具，最终输出通过 Python 校验并以 `completed` 停止，使用 3652 Tokens。
- 两次真实验收和完整测试均未修改四份项目 JSON，也没有执行写入工具。
- 脱敏展示文件使用离线模型替身，不冒充真实千问原始输出。

## 2026-09-19：V1.1 评估与安全基线

主要成果：

- 新增 19 个可运行的脱敏评估案例，包括 6 个正常案例、5 个数据错误或冲突案例和 8 个安全案例。
- 新增 10 组固定评估夹具；运行器只将数据复制到临时目录，不修改项目 JSON。
- 新增批量离线评估运行器，使用真实只读工具、现有 JD Agent 和脚本化模型响应替身执行全部案例。
- 分别汇总结构通过率、来源准确率、匹配一致性、结构化虚构内容接受率、安全拒绝率、安全忽略率和总体安全处理率。
- 提示词注入和伪造 `CONFIRM` 可以被安全忽略；跨用户、跨岗位、任意路径、未授权写入和伪造结构化来源会被拒绝。
- 模型创建或调用失败时明确返回 `model_error`，同时通过 Python 只读工具保留确定性岗位匹配，不伪装成模型分析成功，也不无限重试。

首次代码审阅发现四项评估可信度问题：

- 实际 `matches` 中的证据 ID 被篡改后，来源准确率仍可能错误通过。
- 空 `used_tools` 会因为空集合是允许工具集合的子集而被错误判为安全完成。
- 结构指标复用业务一致性校验，导致来源错误同时降低结构通过率。
- 原“虚构率”直接使用任务是否成功判断，名称和覆盖范围过宽。

修复后增加反例回归：

- 实际匹配来源会与独立夹具真值比较，伪造证据 ID 不再通过。
- 安全完成必须实际执行全部三个受控只读工具且各执行一次。
- 结构指标只检查字段、类型和枚举；来源与匹配指标独立计算。
- 指标收窄为“结构化虚构内容接受率”，只检查伪造要求 ID 和证据 ID。
- 没有独立预期上下文时，来源准确率不会退化为结果与自身比较。
- 案例 Schema 会拒绝结构化虚构检查与模型行为配置不一致的案例。

验证证据：

```text
Ran 124 tests in 0.173s
OK

EVAL_TOTAL=19
EVAL_PASSED=19
STRUCTURE_PASS_RATE=1.0
SOURCE_ACCURACY_RATE=1.0
MATCH_CONSISTENCY_RATE=1.0
STRUCTURED_FABRICATION_ACCEPTANCE_RATE=0.0
SECURITY_HANDLING_RATE=1.0
```

- Python 语法检查和 Git 差异格式检查通过。
- `users.json`、`study_progress.json`、`jobs.json`、`candidate_evidence.json`、`evaluation_cases.json` 和 `evaluation_fixtures.json` 在测试与评估前后均保持不变。
- 新增文件和差异未发现 API Key、Bearer 令牌、联系方式或其他高可信敏感信息。
- V1.1 自动化评估没有调用真实千问，也没有产生 API 费用。
- 19 个固定案例的指标不能推广为真实模型面对任意 JD 时的普遍准确率；自由文本中的全部语义幻觉不在当前结构化虚构指标覆盖范围内。

## 2026-09-20：V1.1.1 离线评估增强

主要成果：

- 在原有 19 个案例上增加 3 个恶意 JD 危险服从案例和 4 个自由文本质量案例，共 26 个固定脱敏案例；10 组夹具不变。
- 增加按配置的禁止声明检查模型生成的解释、学习任务和面试问题；原始学习进度不作为模型生成文本扫描。
- 单案例异常记为失败并继续其余案例，增加执行成功率；异常详情不写入评估报告。
- 评估命令支持 `--case-id`、`--category` 和 `--output`；报告只能新建为 JSON，不覆盖现有文件或项目数据。
- 案例、夹具和报告增加常见手机号、邮箱、本地路径及密钥／令牌格式扫描；审阅中发现并修复中文紧邻密钥、未列入原路径名单的绝对路径两类漏报，并补回归测试。

验证证据：

```text
Ran 142 tests
OK

EVAL_TOTAL=26
EVAL_PASSED=26
EXECUTION_SUCCESS_RATE=1.0
STRUCTURED_FABRICATION_ACCEPTANCE_RATE=0.0
FREE_TEXT_FABRICATION_ACCEPTANCE_RATE=0.75
```

- 26/26 表示评估记录符合预设结果；4 个自由文本适用案例中有 3 个按脚本预期接受了虚构声明，不能解释成产品已阻止虚构。
- 以上均为固定脱敏数据和模型响应替身的离线结果，没有调用真实千问或产生模型费用；自由文本与隐私扫描只覆盖明确配置的声明或常见格式。

## 2026-09-21：V1.2 可信事实层与评估可信度

主要成果：

- 新增只由 Python 确定性匹配和结构化证据生成的 `trusted_facts`；模型自由文本不能写入该结构。
- 可信事实生成重新核对证据技能、能力层级和完整关联集合，并按相同确定性矩阵验证四种状态。
- 将模型解释、学习任务和面试问题整体标记为 `model_generated` 与 `unverified`，避免与能力事实混淆。
- 本地模型错误回退在证据合法时同时保留匹配和可信事实，但不伪造模型分析成功。
- 新增可信事实自由文本泄漏指标；所有汇总指标同时输出分子、分母、适用案例数和比例。
- 审核后将可信事实预期值改为由案例预设和原始夹具独立构造，不再复用生产生成函数；执行异常不计入未泄漏分母。
- 新增正式脱敏评估报告，记录复现命令、案例分类、完整指标和局限说明，并用自动化测试防止报告与当前代码漂移。

验证证据：

```text
Ran 153 tests
OK

FIXED_CASE_EXPECTED_RESULT_AGREEMENT=26/26
FREE_TEXT_FABRICATION_ACCEPTANCE=3/4
TRUSTED_FACT_FREE_TEXT_LEAKAGE=0/4
```

- 以上结果来自固定脱敏数据和模型响应替身，没有调用真实千问或产生模型费用。
- `26/26` 不能表述为任意 JD 准确率；`0/4` 不能表述为模型停止幻觉或已经完成全部事实核查。
