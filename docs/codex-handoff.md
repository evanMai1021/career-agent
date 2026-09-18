# CareerAgent Codex 任务交接记录

更新时间：2026-09-18
暂停时所在分支：`codex/v0.9a-job-evidence-schema`
交接性质：恢复后复核；V0.9a 已完成本地实现与验证，但尚未提交、合并或发布。

## 1. 原始需求

CareerAgent 的总体目标是实现一个面向求职学习场景、可解释且可验证的 Python Agent：

```text
读取脱敏用户资料与学习进度
→ 由受控工具读取或更新本地状态
→ 使用千问生成结构化建议
→ 由 Python 校验工具权限、数据结构、事实来源和写入边界
→ 输出建议、来源、工具记录和执行轨迹
```

项目必须始终区分：

- 岗位提出的要求；
- 候选人已有且可核对的能力证据；
- 正在学习或计划学习的内容；
- 尚未验证的描述；
- 模型生成的建议；
- Python 实际执行的工具和写入操作。

当前开发目标已从 V0.8.1 的数据校验补丁推进到 V0.9a：为后续 JD 匹配建立脱敏的岗位数据、候选人证据数据、验证函数和离线测试。V0.9a 只负责数据契约与校验，不实现岗位匹配，不调用真实模型，也不产生 API 费用。

恢复工作后发现并修复了两个异常类型校验缺口；当前等待用户决定是否提交 Git。

## 2. 已完成步骤

### V0.8.1 已完成并公开

- 拒绝空白的 `target_role`。
- 拒绝空白的现有 `python_progress`、`leetcode_topic` 和 `agent_progress`。
- 拒绝使用空白字符串覆盖文本学习进度。
- 空白写入会在接触真实文件前被拒绝。
- 49 项离线测试通过，测试前后 `users.json` 与 `study_progress.json` 未改变。
- 功能提交：`f07940e fix: reject blank profile and progress text`。
- 文档提交：`9334ec8 docs: finalize V0.8.1 and add roadmap`。
- V0.8.1 已合并到 `main` 并推送至公开仓库：<https://github.com/evanMai1021/career-agent>。
- 当时已核对本地 `HEAD`、上游分支与远程 `main`，三者均为 `9334ec8bbcc50967f86a55a4647ec25984811e67`。

### V0.9a 已完成本地实现与验证，但尚未提交

- 已从 V0.8.1 基线创建分支 `codex/v0.9a-job-evidence-schema`。
- 新增脱敏岗位数据 `jobs.json`。
- 新增脱敏候选人证据数据 `candidate_evidence.json`。
- 新增数据契约与验证模块 `job_data.py`。
- 新增 V0.9a 单元测试 `test_job_data.py`。
- 岗位要求类别限制为 `required` 或 `preferred`。
- 岗位要求优先级限制为整数 1、2、3，并明确拒绝 Python 中会被视为整数子类的布尔值。
- 候选人证据层级限制为 `learning`、`practice`、`project`、`production`。
- `verified` 必须是布尔值。
- 校验重复的岗位 ID、要求 ID、用户 ID 和证据 ID。
- 允许证据列表为空，以真实表达“当前没有证据”，而不是伪造能力或将其误判为数据格式错误。
- 非字符串 `category` 和 `level` 会被稳定拒绝，不会因集合查询抛出 `TypeError`。
- 当前只建立数据边界；尚未实现 `matched`、`partial`、`missing`、`unverified` 的匹配计算。

## 3. 已修改文件及主要变化

以下是暂停时工作区中与 V0.9a 有关的未提交内容：

| 文件 | Git 状态 | 主要变化 |
|---|---|---|
| `job_data.py` | 未跟踪 | 新增岗位、岗位要求、候选人证据及两份 JSON 根结构的验证函数；校验精确字段、非空字符串、枚举值、优先级、布尔验证状态和重复 ID。 |
| `test_job_data.py` | 未跟踪 | 新增 17 项数据契约测试，覆盖合法数据、项目 JSON、空白值、非法枚举、错误枚举类型、重复 ID、布尔优先级、非法验证状态和空证据列表。 |
| `jobs.json` | 未跟踪 | 新增一个脱敏 AI Agent 岗位示例，包含 Python、Agent 工具调用和 FastAPI 等结构化要求。 |
| `candidate_evidence.json` | 未跟踪 | 新增 `test_user` 脱敏证据；Python 与 Agent 工具调用记录为项目证据，FastAPI 只记录为学习计划且 `verified=false`。 |
| `PROJECT_STATUS.md` | 已修改 | 记录 V0.9a 已通过 17 项目标测试与 66 项完整测试、数据未改变、未调用模型，以及下一步 Git 边界。 |
| `ROADMAP.md` | 已修改 | 将原 V0.9 拆分为 V0.9a 数据契约与 V0.9b 确定性匹配，补充各阶段目标、边界、验收与学习映射。 |
| `README.md` | 已修改 | 增加 V0.9a 数据契约、阶段边界和验证结果。 |
| `CAREER_AGENT_HISTORY.md` | 已修改 | 记录 V0.9a 实现、缺口修复、测试证据和 Codex 协助边界。 |
| `CAREER_AGENT_HANDOFF.md` | 本地协作文档，Git 忽略 | 已同步本地候选进度和下一检查点；它不出现在普通 `git status` 中。 |
| `docs/codex-handoff.md` | 本次新增 | 保存本交接记录；没有修改业务逻辑。 |

V0.8.1 已提交的相关文件包括 `main.py`、`test_main.py`、`PROJECT_STATUS.md`、`PROJECT_SCOPE.md`、`CAREER_AGENT_HISTORY.md`、`README.md`、`ROADMAP.md` 和 `study_progress.json`。不要把这些已发布变化与当前未提交的 V0.9a 候选改动混为一谈。

## 4. 当前 Git 状态

本次写入交接文档前的现场状态：

```text
## codex/v0.9a-job-evidence-schema
 M CAREER_AGENT_HISTORY.md
 M PROJECT_STATUS.md
 M README.md
 M ROADMAP.md
?? candidate_evidence.json
?? docs/codex-handoff.md
?? job_data.py
?? jobs.json
?? test_job_data.py
```

当前 `HEAD`：

```text
9334ec8 docs: finalize V0.8.1 and add roadmap
```

`HEAD` 与 `main`、`origin/main`、`origin/HEAD` 目前都指向 `9334ec8`。这说明 V0.9a 业务改动尚未形成提交，也未合并或推送。

当前工作区不是干净状态。不要在新会话中执行重置、回退、清理未跟踪文件或覆盖式操作。

## 5. 已运行的测试及结果

### V0.8.1 验证记录

使用项目虚拟环境 `.venv\Scripts\python.exe` 运行完整离线测试：

```text
Ran 49 tests in 0.056s
OK
TEST_EXIT=0
USERS_UNCHANGED=True
PROGRESS_UNCHANGED=True
```

当次记录的 SHA-256：

```text
users.json
7D664D6A8BB1FE8DE8244E2E4627E354F4D52A374864CFFFCF5A9490AA73C900

study_progress.json
8B3F722C652408AC26DC05CCFAC8E9E01F6CB14EDC7AA01D98C9B1ACA9A5F731
```

### V0.9a 最终验证记录

代码审阅先使用两个定向测试复现非字符串枚举值导致的崩溃：

```text
Ran 2 tests in 0.002s
FAILED (errors=2)
```

修复为先检查字符串类型再查询枚举集合后，两项定向回归测试通过。随后运行 V0.9a 目标测试与完整离线测试：

```text
Ran 17 tests in 0.004s
OK

Ran 66 tests in 0.062s
OK
TEST_EXIT=0
COMPILE_EXIT=0
users.json_UNCHANGED=True
study_progress.json_UNCHANGED=True
jobs.json_UNCHANGED=True
candidate_evidence.json_UNCHANGED=True
```

直接验证两份新数据时还得到：

```text
JOBS_VALID=True
EVIDENCE_VALID=True
```

以上 V0.9a 测试均为离线测试，没有调用千问、没有产生 API 费用，也没有修改四份 JSON 数据。PowerShell 中中文文档字符串曾出现乱码显示，但测试名称、断言、退出码和结果均正常；该显示问题不是 Python 运行失败。后续若业务文件再次变化，必须重新运行完整测试并重新核对数据哈希。

## 6. 尚未解决的问题

### V0.9a Git 操作尚未授权

- 用户在讲解和提示后能够区分学习计划、未验证证据与可匹配证据，但不能记录为独立闭卷掌握。
- V0.9a 完整差异、安全边界、公开数据和异常类型已经复核。
- `README.md`、`CAREER_AGENT_HISTORY.md`、`PROJECT_STATUS.md` 和 `ROADMAP.md` 已同步本地验证结果。
- V0.9a 尚未获得用户对 Git 提交的明确授权；合并和推送也尚未授权。
- 当前交接文档本身尚未提交。

### V0.9b 尚未开始

- 尚未实现读取岗位要求的只读工具。
- 尚未实现读取候选人证据的只读工具。
- 尚未实现确定性的 `match_job_requirements`。
- 尚未定义并验证 `matched`、`partial`、`missing`、`unverified` 的完整判定矩阵。
- 尚未接入 `main.py` 或千问流程；这是有意保持的阶段边界。

### 数据真实性边界

- Schema 只能要求每条证据包含来源、层级和验证状态，不能自动证明文字内容真实。
- `ROADMAP.md` 中的计划不是能力证据。
- `verified=false` 的内容不能直接支持 `matched`。
- 当前 FastAPI 仅是学习计划，不得宣传为已掌握、已用于项目或已具备生产经验。

## 7. 下一阶段的执行顺序

1. 最后检查 Git 状态、完整差异、密钥与隐私扫描结果。
2. 询问用户是否暂存并提交已经验证的 V0.9a；未经明确授权不执行提交。
3. 合并与推送分别等待用户后续授权，不能从“允许提交”推断获得授权。
4. V0.9a 提交后再创建 V0.9b 功能分支，以测试优先方式实现 Python 控制的确定性匹配。
5. V0.9b 仍保持离线；真实模型调用留到后续 Agent 化阶段，并在调用前重新取得费用与密钥边界确认。

## 8. 不能修改的内容

暂停期间和恢复工作的第一轮检查中，必须遵守以下边界：

- 不得修改、删除、覆盖或回退当前未提交的 V0.9a 文件和用户已有改动。
- 不得使用破坏性 Git 命令清理工作区，不得删除未跟踪文件。
- 未经用户明确授权，不得提交、合并、推送或改写 Git 历史。
- 不得读取、展示、提交或记录 `.env`、API Key、令牌、Cookie、验证码等敏感信息。
- 不得把真实姓名、联系方式、投递记录或其他个人隐私写入公开演示 JSON。
- 不得把学习计划、阅读记录或版本路线图当成已掌握能力。
- 不得让 `verified=false` 的证据直接进入 `matched`。
- 匹配状态必须由可测试的 Python 规则决定，不能交给模型自由判断或篡改。
- 不得让模型指定任意用户名、岗位、文件路径或扩大工具权限。
- 不得破坏 V0.8.1 已验证的受控写入链路：模型提案、Python 校验、参数预览、精确 `CONFIRM`、实际写入、磁盘重读和执行记录。
- 未经确认，不得新增依赖、框架或外部服务；尤其不要提前加入 FastAPI、数据库、RAG、多 Agent、网页前端、自动岗位搜索、自动投递或云部署。
- 不得把 Codex 协助实现的代码描述为用户独立实现或已经完全掌握。
- 不得仅根据版本号、文档或文件存在就宣称功能完成；完成状态必须以实际运行、测试、数据不变和用户验收为证据。

## 9. 新会话开始时需要优先读取的文件

建议严格按以下顺序读取：

1. `AGENTS.md`：项目协作、安全、教学和完成状态规则。
2. `docs/codex-handoff.md`：本次暂停时的完整现场记录。
3. `CAREER_AGENT_HANDOFF.md`：本地项目交接入口；该文件可能被 Git 忽略。
4. `PROJECT_STATUS.md`：当前开发状态与真实验收记录。
5. `ROADMAP.md`：V0.9a、V0.9b 及后续阶段边界。
6. `PROJECT_SCOPE.md`：第一版包含与不包含的范围。
7. 当前 Git 状态、最近提交和工作区差异。
8. `job_data.py` 与 `test_job_data.py`：V0.9a 候选实现和测试。
9. `jobs.json` 与 `candidate_evidence.json`：脱敏岗位和候选人证据数据。
10. `main.py` 与 `test_main.py`：V0.8.1 现有主流程、验证、工具和回归基线。
11. 只有在核对模型边界时再读取 `qwen_agent.py`。

无需在新会话开始时扫描全部 `notes`；只有核对某项具体学习证据时，才读取对应的最近笔记。

## 恢复工作时的最小开场检查

```text
确认项目根目录 D:\Projects\agent_project
→ 读取交接入口与状态文档
→ 检查当前分支、未提交文件和差异
→ 确认 V0.9a 尚未提交且 V0.9b 尚未开始
→ 完成数据真实性边界验收
→ 再决定是否继续修改、测试或提交
```

本交接记录生成时未继续修改任何业务代码、测试代码或项目数据。
