# CareerAgent

CareerAgent 是一个面向求职学习场景的 Python Agent 项目。它会读取脱敏的学习进度，让千问模型选择只读工具，并输出 Python、LeetCode 和 Agent 三类结构化建议。

## 文档导航

- 当前功能、验证结果和下一步：[`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- 第一版包含与不包含的范围：[`PROJECT_SCOPE.md`](PROJECT_SCOPE.md)
- 版本演进与历史验证证据：[`CAREER_AGENT_HISTORY.md`](CAREER_AGENT_HISTORY.md)

## 当前功能

- 加载并验证用户基础资料。
- 使用 `get_study_progress` 读取指定用户的学习进度。
- 已实现受白名单约束的本地更新工具 `update_study_progress`，但尚未开放给模型自动调用。
- 使用千问 `qwen3.8-flash` 进行 Function Calling（函数调用）。
- 使用 JSON Schema 约束模型输出结构。
- 限制 Agent 最大循环步数，并记录工具、轨迹和停止原因。
- 保留不产生 API 费用的本地规则模式。

当前 LLM 循环只向模型开放 `get_study_progress`。写入工具不会被模型自动调用。

## 环境

- Python 3.13
- Windows / PowerShell
- 千问 AI 平台 OpenAI 兼容接口

## 安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制 `.env.example` 为 `.env`，然后只在本地填写：

```ini
DASHSCOPE_API_KEY=你的千问API密钥
CAREER_AGENT_MODE=llm
```

`.env` 已被 `.gitignore` 忽略。请勿把真实密钥写入代码、截图或提交记录。

## 运行

```powershell
.venv\Scripts\python.exe main.py
```

按提示输入演示用户名：

```text
test_user
```

如需使用完全本地、无 API 费用的规则模式，将 `.env` 中的模式改为：

```ini
CAREER_AGENT_MODE=rule
```

## 测试

```powershell
.venv\Scripts\python.exe -m unittest -v
```

单元测试使用模型响应替身，不会真实调用千问，也不会产生模型费用。

## 数据流

```text
启动 main.py
→ 加载并验证用户
→ 千问判断是否需要学习进度
→ 调用 get_study_progress
→ 将工具结果返回千问
→ 千问生成结构化建议
→ 本地再次验证建议结构
→ 输出结果、工具记录、Token 用量和循环轨迹
```

## 项目边界

- 当前只有千问模型能选择只读工具，写入操作仍由程序显式控制。
- 当前没有 RAG、多 Agent、网页前端、自动岗位搜索或自动投递。
- `used_tools` 记录实际执行过的工具；`trace` 同时记录模型决策和程序动作。
