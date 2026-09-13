# CareerAgent 开发历史

本文件按版本记录 CareerAgent 已经完成并有证据支持的开发过程。当前状态和下一步请查看 `PROJECT_STATUS.md`；本文件中的“尚未完成”只表示当时版本的边界，不代表现在仍未完成。

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

## 当前版本之后的候选工作

以下内容没有包含在上述已完成版本中，应以当前 `PROJECT_STATUS.md` 为准决定是否实施：

- 为写入工具增加明确意图、参数预览和用户确认。
- 改善复习任务的数据结构和模型建议事实准确性。
- 保存 README 运行截图。
- 如需公开发布，创建远程仓库并在推送前再次检查公开内容。

第一版范围仍不包含 RAG、多 Agent、网页前端、自动岗位搜索、自动投递和云部署。

## 2026-09-14：本地 Git 基线

- 在 `D:\Projects\agent_project` 初始化本地 Git 仓库，默认分支为 `main`。
- 使用个人全局 Git 身份创建首次提交：`ce8cba2 feat: add CareerAgent V0.5`。
- 首次提交包含 16 个公开项目文件；`.env`、虚拟环境、IDE 配置、私人学习记录和本地协作文档均由 `.gitignore` 排除。
- 提交前使用项目虚拟环境运行 26 项离线测试，结果为 `OK`。
- 当前尚未创建或连接 GitHub 等远程仓库，代码仍只保存在本地。
