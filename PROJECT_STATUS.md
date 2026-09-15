# CareerAgent 项目状态

## CareerAgent V0.8

更新时间：2026-09-16

当前建议流程：

```text
加载并验证用户
→ 千问判断是否需要学习进度
→ 模型请求 get_study_progress
→ Python 执行只读工具
→ 工具结果返回千问
→ 千问按照 JSON Schema 生成三类建议及 sources
→ 本地再次验证建议结构和来源是否与工具结果一致
→ 输出工具记录、循环轨迹、Token 用量和建议
```

当前受控更新流程：

```text
加载并验证用户
→ 用户明确选择 update 并输入更新要求
→ 千问生成 update_study_progress 参数提案
→ Python 验证用户名范围、字段白名单和值类型
→ 输出待确认提案
→ 用户输入精确确认词 CONFIRM
→ Python 执行 update_study_progress 并保存
→ 输出确认、工具执行和停止原因
```

已完成：

- 使用千问 AI 平台 `qwen3.8-flash` 的 OpenAI 兼容接口。
- 千问实际选择并调用 `get_study_progress`，不再只是规则程序固定调用。
- 工具完成后切换到严格 JSON Schema 生成阶段。
- Python、LeetCode、Agent 三类建议统一包含 `task` 和 `reason`。
- 模型只能查询当前已验证用户名，不能指定任意文件路径或其他用户。
- LLM 循环保留 `max_steps`、工具错误停止、输出校验和执行轨迹。
- 最终输出包含 `model` 和 `llm_usage`，可以核对实际模型与 Token 用量。
- 原有规则循环仍可通过 `CAREER_AGENT_MODE=rule` 使用，不产生 API 费用。
- 第二个工具 `update_study_progress` 已实现，但没有开放给模型自动调用。
- 模型相关自动化测试使用响应替身，不产生 API 费用。
- 千问真实运行验收通过：调用只读工具、生成结构化建议并以 `completed` 停止。
- 真实验收使用 885 Tokens；脱敏结果保存在 `examples/careeragent_v0_5_qwen_output.json`。
- 已新增 README、依赖文件和无密钥的环境变量示例。
- 已初始化本地 Git 仓库，当前分支为 `main`。
- 首次提交前已检查待跟踪文件，`.env`、私人学习记录和本地协作文档均未进入版本历史。
- `review_tasks` 已从题号字符串列表升级为包含 `problem_id`、`title`、`topic` 的字典列表。
- 读取和更新工具都会验证每项复习任务的结构、字段集合、字符串类型和非空值。
- 工具只向模型返回三个约定字段，避免额外数据混入提示上下文。
- 模型提示词明确区分当前主线专题与每道复习题的真实专题，并限制原因只能引用工具事实。
- 复习任务结构相关测试覆盖旧结构、缺少字段、空白专题和合法更新。
- 真实模型回归通过：560 被识别为前缀和与哈希表，283 被识别为双指针；本次使用 1032 Tokens。
- 用户现在可以选择 `advice` 或 `update`；直接回车仍默认进入只读建议流程。
- `update` 只在用户明确提出写入意图后，让千问生成一个受 Schema 约束的参数提案。
- Python 会再次验证提案中的当前用户名、字段白名单和值结构。
- 提案结果用 `requested_tools` 记录模型请求；确认前或取消时，`used_tools` 必须为空。
- 只有精确输入 `CONFIRM` 才执行更新；其他输入统一取消并以 `user_cancelled` 停止。
- 确认后会执行 `update_study_progress`，并将工具加入 `used_tools`；写入失败则以 `tool_error` 停止。
- 模型提案、用户确认和写入工具会合并为一条可审计的 `trace`。
- 41 项离线自动化测试通过，覆盖合法提案、越权用户名、非法值、取消、确认、写入失败和主流程。
- 确认流程已与真实写入工具在临时 JSON 上完成集成验证，没有修改项目演示数据。
- 真实更新提案验收通过，状态为 `confirmation_required`，使用 579 Tokens。
- 真实验收前后 `study_progress.json` 的 SHA-256 均为 `4C318043A3B3588CE1931F101B238A14DF151B2239C7CB1BC064B9CAFD59D0FD`，证明提案阶段没有写入。
- 脱敏提案保存在 `examples/careeragent_v0_7_update_proposal_output.json`。
- 用户已在真实主流程中核对提案并输入 `CONFIRM`，写入工具以 `success` 完成，本次使用 583 Tokens。
- 磁盘中的 `agent_progress` 已更新为“CareerAgent V0.7已完成受控写入确认流程”，其他学习进度字段保持不变。
- 写入后重新加载 JSON 成功，41 项离线测试再次通过。
- 成功读取测试已改用临时固定数据，避免正常更新演示进度导致断言过期。
- 脱敏确认结果保存在 `examples/careeragent_v0_7_confirmed_update_output.json`。
- `review_tasks` 已升级为 `problem_id` 整数、`title`、`topics` 列表和 `status`。
- 本地可信目录固定校验 560、283、76、438、239 的真实题名和专题。
- 未知题号、错误题名、错误专题、重复专题和不合法结构都会在进入模型前被拒绝。
- 模型建议现在必须携带 `sources`，Python 会与读取工具的原始结果精确比较。
- 模型替身把 560 错误关联为双指针时，本地输出校验会拒绝结果，并且不会再次调用 API。
- `update_study_progress` 写入后会在程序内部重新读取磁盘；回读失败或不一致时不返回完成。
- 46 项离线自动化测试通过；事实映射和错误来源测试均使用模型替身，没有调用真实 API。
- 用户随后真实运行现有受控更新流程，使用 610 Tokens；参数提案、精确 `CONFIRM`、写入执行、`status=completed` 和 `stop_reason=completed` 均已验证。
- 新增建议 `sources` Schema 已通过一次真实千问验收：模型调用 `get_study_progress` 后生成三类建议，Python 成功核对全部来源并以 `completed` 停止。
- 本次真实只读验收使用 1292 Tokens，其中输入 839 Tokens、输出 453 Tokens；没有调用写入工具。

尚未完成：

- 如需公开发布，创建远程仓库并在推送前再次检查公开内容。

展示证据：

- README 已加入一张脱敏的受控写入代表性截图，展示参数提案、精确确认、实际工具记录和完成状态。
- 测试与安全检查结论使用文字或命令输出留证，无需分别截图。

## 已解决的数据质量问题

V0.5 的 `review_tasks` 只保存题号，模型曾错误地把 560 和 283 都关联到“滑动窗口”。V0.6 增加了题名和专题，但只验证非空结构，没有验证语义映射。V0.8 改为本地可信目录和结构化来源核对，错误题号或专题不会直接进入最终建议。

程序运行成功仍不等于所有建议天然正确；后续新增数据字段时仍需保持结构验证和真实回归。

## 下一步顺序

1. 决定是否创建远程仓库并公开 V0.8。
2. 推送前重新检查提交内容、密钥忽略状态和演示数据。

## 边界说明

只读建议流程已经形成真实的 Function Calling（函数调用）：模型返回工具名称和参数，Python 程序验证权限并执行工具，再把结果交还模型。

更新流程必须依次经过“用户明确选择更新、模型生成提案、Python 校验、用户输入 `CONFIRM`”四道约束。只有全部通过后 Python 才执行写入工具；模型仍然没有任意文件权限。

模型提案、用户确认和 Python 写入已经完成一次真实端到端验收。`requested_tools` 和 `used_tools` 均记录 `update_study_progress`，执行轨迹依次记录提案、确认和写入成功。

当前没有使用 RAG、多 Agent、网页前端、自动岗位搜索或自动投递。

## 2026-09-16 GitHub 推送前检查

已确认：

- `.env` 命中 `.gitignore`，且不在 Git 跟踪列表中。
- Git 可见文件未发现高可信 API Key、Bearer 令牌或 Cookie 内容。
- `users.json` 和 `study_progress.json` 只包含 `test_user` 脱敏演示数据。
- 两份 V0.7 运行证据不含密钥、联系方式或完整本机路径。
- Git 跟踪列表中没有 `.tmp`、`__pycache__`、`.pyc`、`.idea` 或 `.env`。
- 当前没有配置远程仓库，因此本次不推送。

当前 Git 边界：

- V0.8 已完成本地 Git 版本记录。
- 当前没有远程仓库，本次也没有获得公开推送授权。

结论：安全内容检查通过，但仓库暂不进入公开推送步骤。该结论以文字和命令检查结果留证，不需要单独截图。
