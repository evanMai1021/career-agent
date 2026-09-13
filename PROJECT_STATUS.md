# CareerAgent 项目状态

## CareerAgent V0.5

更新时间：2026-09-14

当前默认流程：

```text
加载并验证用户
→ 千问判断是否需要学习进度
→ 模型请求 get_study_progress
→ Python 执行只读工具
→ 工具结果返回千问
→ 千问按照 JSON Schema 生成三类建议
→ 本地再次验证建议结构
→ 输出工具记录、循环轨迹、Token 用量和建议
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
- 26 项自动化测试通过；模型相关测试使用替身，不产生 API 费用。
- 千问真实运行验收通过：调用只读工具、生成结构化建议并以 `completed` 停止。
- 真实验收使用 885 Tokens；脱敏结果保存在 `examples/careeragent_v0_5_qwen_output.json`。
- 已新增 README、依赖文件和无密钥的环境变量示例。

尚未完成：

- 带有用户明确写入意图和确认步骤的更新工具调用分支。
- README 运行截图。
- Git 仓库初始化与公开发布检查。

## 边界说明

当前已经形成真实的 Function Calling（函数调用）：模型返回工具名称和参数，Python 程序验证权限并执行工具，再把结果交还模型。

这仍然是受控的单模型、单只读工具循环，不代表模型拥有任意文件权限。`update_study_progress` 不在模型工具列表中，因此模型无法自动修改本地学习记录。

当前没有使用 RAG、多 Agent、网页前端、自动岗位搜索或自动投递。
