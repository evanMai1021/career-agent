# 代码目录与开发导航

目录整理保留 V1.9.2 的业务边界；常用启动入口保留在项目根目录，原 JSON 数据、examples 和本地私人资料不搬动。另新增 [统一启动入口](UNIFIED_STARTUP.md)，只管理现有独立服务，不增加业务 HTTP 接口、依赖或匹配规则。

## 目录分类

```text
career_agent/              Python 业务实现
  core/                    岗位／证据结构校验、确定性匹配
  agents/                  千问连接、受控工具循环、岗位分析 Agent
  imports/                 PDF／TXT／DOCX 提取、JSON 整理、字段提示
  services/                本机 API、演示与私有资料服务
  evaluation/              离线评估、评估运行器、有限隐私检查
  cli/                     交互命令行实现
  paths.py                 仓库数据与网页位置
web/                       三个网页文件
tests/                     Python 测试与虚构响应辅助函数
  web/                     三个网页的 Node.js 脚本测试
docs/                      当前说明、验证证据、版本历史
examples/                  公开脱敏／虚构示例
根目录 *.json              现有数据与固定评估集（位置不变）
```

每个 Python 子目录中的 `__init__.py` 用于标识包，不负责启动服务或运行模型。`notes/` 仍是本地忽略目录，不属于公开资料。

## 按修改目标找文件

| 想修改什么 | 实现位置 | 主要测试 |
|---|---|---|
| 岗位和证据字段、四态判定 | [job_data.py](../career_agent/core/job_data.py)、[job_matching.py](../career_agent/core/job_matching.py) | [test_job_data.py](../tests/test_job_data.py)、[test_job_matching.py](../tests/test_job_matching.py) |
| 模型连接、工具确认与岗位分析 | [qwen_agent.py](../career_agent/agents/qwen_agent.py)、[job_analysis_agent.py](../career_agent/agents/job_analysis_agent.py)、[cli/main.py](../career_agent/cli/main.py) | [test_main.py](../tests/test_main.py)、[test_job_analysis_agent.py](../tests/test_job_analysis_agent.py) |
| 文件提取、JSON 整理与字段提示 | [imports](../career_agent/imports/)、[导入服务](../career_agent/services/file_import_server.py) | [test_file_importer.py](../tests/test_file_importer.py)、[test_text_json_formatter.py](../tests/test_text_json_formatter.py)、[test_draft_validation_hints.py](../tests/test_draft_validation_hints.py) |
| 导入页编辑、错误跳转和筛选 | [file_import.html](../web/file_import.html) | [test_file_import_page.cjs](../tests/web/test_file_import_page.cjs) |
| 原演示 API、历史资料和模拟案例 | [api_app.py](../career_agent/services/api_app.py)、[demo_cases.py](../career_agent/services/demo_cases.py)、[demo_profile.py](../career_agent/services/demo_profile.py)、[demo.html](../web/demo.html) | [test_api_app.py](../tests/test_api_app.py)、[test_demo_page.cjs](../tests/web/test_demo_page.cjs) |
| 私有 JSON 分析和资料页面 | [private_case_runner.py](../career_agent/services/private_case_runner.py)、[private_case_server.py](../career_agent/services/private_case_server.py)、[private_demo.html](../web/private_demo.html) | [test_private_case_runner.py](../tests/test_private_case_runner.py)、[test_private_case_server.py](../tests/test_private_case_server.py)、[test_private_demo_page.cjs](../tests/web/test_private_demo_page.cjs) |
| 离线评估与报告 | [evaluation](../career_agent/evaluation/) | [test_job_analysis_evaluation.py](../tests/test_job_analysis_evaluation.py) |
| 目录、旧入口与资源路径 | [paths.py](../career_agent/paths.py) | [test_project_layout.py](../tests/test_project_layout.py) |
| 统一启动、就绪与退出回收 | [start_services.py](../career_agent/cli/start_services.py)、[managed_worker.py](../career_agent/services/managed_worker.py) | [test_start_services.py](../tests/test_start_services.py) |

新增业务代码使用完整包路径，例如 `from career_agent.core.job_matching import match_job_requirements`；Python 测试之间的辅助函数使用 `from tests.test_text_json_formatter import ...`。不要将新业务逻辑写回根目录兼容入口。

## 原有启动方式保持不变

在项目根目录的 PowerShell 中运行：

```powershell
# 交互命令行；模型模式可能产生费用，规则模式无需密钥
.venv\Scripts\python.exe main.py

# 原本机演示 API
.venv\Scripts\python.exe -m uvicorn api_app:app --host 127.0.0.1 --port 8000

# 默认文件提取与校对，不调用模型
.venv\Scripts\python.exe -X utf8 file_import_server.py --port 8002

# 纯虚构 JSON 模板的本机资料页
.venv\Scripts\python.exe -X utf8 private_case_server.py --case-file examples/careeragent_v1_7_private_case_template.json --port 8001

# 固定夹具离线评估，不调用真实模型
.venv\Scripts\python.exe -X utf8 job_analysis_evaluation_runner.py
```

对应网页为 `http://127.0.0.1:8000/demo`、`http://127.0.0.1:8002/import` 和 `http://127.0.0.1:8001/private`。终端保持开启，结束按 `Ctrl+C`。仍只用于本机虚构／脱敏资料，没有身份验证，不用于公网或共享电脑。可选模型整理的启动开关、费用与明确同意边界见 [文件导入说明](FILE_IMPORT.md)。

根目录原有六个 Python 文件仅兼容旧入口，另有新增的 `start.py` 统一启动入口；实际实现分别在 `career_agent/cli/`、`services/`、`evaluation/`。也可从根目录使用 `python -m career_agent.services.file_import_server --port 8002`；不要直接运行包内部文件路径，以免缺少包导入环境。

## 测试方式

完整 Python 测试仍可自动发现：

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest discover
```

只测试一个模块，需加 `tests.` 前缀；网页测试需使用新位置：

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest tests.test_file_import_server tests.test_project_layout
node --test tests/web/test_demo_page.cjs tests/web/test_private_demo_page.cjs tests/web/test_file_import_page.cjs
```

Node.js 仍仅用于开发测试，不是应用运行依赖。历史记录中的旧文件位置／单模块测试命令属于当时结构；当前入口以本页为准。目录调整不代表真实资料准确性或个人能力验收完成。

目录整理阶段验证：330 项 Python 测试（原 325 项与新增 5 项目录兼容回归）、121 项网页脚本通过；原交互命令行的规则模式、虚构模板终端分析、26 个固定案例离线评估均运行成功，原 `api_app:app` 经 Uvicorn 配置加载通过。三个网页内容哈希保持一致。没有重新进行浏览器交互或真实模型调用，不将目录整理记作新的模型能力验收。

统一启动新增 25 项测试，当前完整 Python 回归为 355 项，网页脚本仍为 121 项；实际验证仅使用虚构模板和本机服务，见 [统一启动说明](UNIFIED_STARTUP.md)。
