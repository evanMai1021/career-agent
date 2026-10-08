# CareerAgent 项目证据与讲解

本页供查看公开代码和准备项目介绍时使用。所有结论只覆盖仓库中的实现、脱敏数据与已记录的验证；个人简历还需按本人实际参与内容调整。仓库中有代码，不代表任何人独立完成了对应实现。

## 项目主张与证据

| 可核对的项目主张 | 代码 | 测试或演示 | 可以怎样介绍 | 不应怎样介绍 |
|---|---|---|---|---|
| 受控工具调用与确认写入 | [`main.py`](../main.py)、[`qwen_agent.py`](../qwen_agent.py)、[`job_analysis_agent.py`](../job_analysis_agent.py) | [`test_main.py`](../test_main.py)、[`test_job_analysis_agent.py`](../test_job_analysis_agent.py)、[脱敏确认示例](../examples/careeragent_v0_7_confirmed_update_output.json) | 模型提出工具请求，Python 检查范围和参数；本地更新需要用户输入 `CONFIRM`。 | 模型拥有任意文件权限，或写入会自动发生。 |
| 四态岗位匹配 | [`job_data.py`](../job_data.py)、[`job_matching.py`](../job_matching.py) | [`test_job_data.py`](../test_job_data.py)、[`test_job_matching.py`](../test_job_matching.py)、[匹配示例](../examples/careeragent_v0_9b_job_match_output.json) | 对经过结构校验的脱敏岗位要求和候选人证据，按相同 `skill_id`、证据层级与验证标记计算 `matched`、`partial`、`unverified`、`missing`。 | 能理解任意自然语言 JD，或能自动证明候选人真实能力。 |
| 可信事实与模型建议分层 | [`job_analysis_agent.py`](../job_analysis_agent.py)、[`job_analysis_evaluation.py`](../job_analysis_evaluation.py) | [`test_job_analysis_agent.py`](../test_job_analysis_agent.py)、[`test_job_analysis_evaluation.py`](../test_job_analysis_evaluation.py)、[离线评估报告](../examples/careeragent_v1_2_evaluation_report.json) | `trusted_facts` 只包含 Python 核对的要求、状态和证据 ID；模型解释与建议另行标为未验证。 | 已消除模型幻觉，或模型自由文本都经过完整事实核查。 |
| 固定案例离线评估 | [`job_analysis_evaluation_runner.py`](../job_analysis_evaluation_runner.py)、[`job_analysis_evaluation.py`](../job_analysis_evaluation.py) | [`test_job_analysis_evaluation.py`](../test_job_analysis_evaluation.py)、[26 案例报告](../examples/careeragent_v1_2_evaluation_report.json) | 用模型响应替身运行 26 个固定脱敏案例，并公开各指标的分子、分母和适用案例数。 | `26/26` 等于任意 JD 的准确率；报告中的 `0/4` 等于完整幻觉治理。 |
| 本机只读 API | [`api_app.py`](../api_app.py) | [`test_api_app.py`](../test_api_app.py)、[完整脱敏响应](../examples/careeragent_v1_3_api_analysis_output.json) | 提供健康检查、岗位要求查询与本机离线确定性分析；HTTP 请求不能选择数据文件或模型。 | 已有登录系统、生产部署、任意 JD 接入或真实候选人数据服务。 |
| 本机输入与判定过程展示 | [`api_app.py`](../api_app.py)、[`demo_cases.py`](../demo_cases.py)、[`demo.html`](../demo.html) | [`test_demo_cases.py`](../test_demo_cases.py)、[`test_demo_page.cjs`](../test_demo_page.cjs)、[模拟拒绝截图](images/careeragent-v1-6-simulated-rejection.jpg) | 切换五个模拟输入，查看证据来源、真实规则判定、执行步骤和预设／实际核对；请求有超时与恢复提示。 | 模拟案例代表真实个人能力或任意 JD 准确率；页面支持真实用户登录或公网使用。 |
| 完整历史用户资料展示 | [`demo_profile.py`](../demo_profile.py)、[`demo.html`](../demo.html) | [`test_demo_profile.py`](../test_demo_profile.py)、[历史资料截图](images/careeragent-v1-6-historical-user-profile.jpg) | 查看固定历史用户的全部演示字段，将已验证证据、待核实描述和学习记录分别展示。 | 已经核实用户当前全部能力，或历史项目测试数证明个人独立掌握。 |
| 本机私有结构化资料分析 | [`private_case_runner.py`](../private_case_runner.py)、[`private_case_server.py`](../private_case_server.py)、[`private_demo.html`](../private_demo.html) | [`test_private_case_runner.py`](../test_private_case_runner.py)、[`test_private_case_server.py`](../test_private_case_server.py)、[`test_private_demo_page.cjs`](../test_private_demo_page.cjs)、[`test_private_case_template.py`](../test_private_case_template.py)、[纯虚构模板](../examples/careeragent_v1_7_private_case_template.json)、[运行与输入说明](PRIVATE_CASES.md) | 明确指定手工脱敏 JSON，使用同一快照展示全部输入证据、关联结果及可信事实；资格分离，可选人工预设核对，不调用模型或写文件。 | 自动理解任意 JD、解析原始 PDF、证明简历声明真实，或已经具备认证和公网候选人服务。 |

这些是**项目能力**的证据映射，不证明任何人的独立编码程度。简历中的“独立设计”“独立实现”等个人贡献表述，须另有本人完成过程的证据。

V1.8 文件文字导入：[`file_importer.py`](../file_importer.py)、[`file_import_server.py`](../file_import_server.py) 和 [`file_import.html`](../file_import.html) 提供本机 PDF／TXT／DOCX 文字提取与人工校对；[`test_file_importer.py`](../test_file_importer.py)、[`test_file_import_server.py`](../test_file_import_server.py)、[`test_file_import_page.cjs`](../test_file_import_page.cjs) 验证解析及交互边界。可介绍为“有位置标记、限额及固定错误提示的本机文字预览”；不能介绍为“完整简历解析、能力核实或文件自动参与岗位分析”。运行见 [FILE_IMPORT.md](FILE_IMPORT.md)。

可选 JSON 整理：[`text_json_formatter.py`](../text_json_formatter.py) 和 [`test_text_json_formatter.py`](../test_text_json_formatter.py) 验证确认后的修正文字、外发同意、描述摘录、字段约定、缺项处理与全部证据 false。2026-10-07 另通过真实浏览器完成一次纯虚构文字的千问联调及本地 JSON 反例，见 [FILE_IMPORT.md](FILE_IMPORT.md)。可以介绍“在明确同意后由模型辅助整理待复核草稿，再本地校验；一次虚构案例联调成功”；不能声称“任意真实简历已验收、技能映射准确或描述出现就证明能力”。没有自动保存／分析，任意文字语义准确性仍待验收。

V1.8.1 校对交互：现有导入页、服务和格式化测试验证等宽加高编辑区、缺项列表、固定错误分类与成功后再次生成的费用确认。2026-10-09 的真实浏览器验收只使用虚构资料和模型响应替身，没有再次调用真实模型。可介绍“降低草稿校对与误重复请求风险”，不能声称“保证不会收费、隐私已完全清除或模型引用通过就证明能力”。

## 数据流与技术决策

```text
本机演示页：打开 /demo → 加载模拟输入和预设 → 选择案例 → POST /demo/analyses
                       → 校验拒绝，或计算匹配与可信事实 → 分开显示执行、判定原因和案例核对
本地 API：请求用户名与岗位 ID → 固定文件 → 结构校验 → Python 匹配与 trusted_facts → 只读响应
独立私有入口：明确指定脱敏 JSON → 校验与内存快照 → Python 匹配、可信事实及可选预设核对
                                          → 终端或 /private 展示输入与关联证据（无模型、无写入）
JD Agent：限定范围 → 模型请求三个只读工具 → Python 执行并校验 → Python 计算匹配状态
                                                        → 模型生成建议（未验证）→ Python 核对输出
                                                        → Python 从匹配和证据生成 trusted_facts

本地更新：用户选择 update → 模型提出参数 → Python 校验并展示 → 用户输入 CONFIRM → 写入与回读
```

1. **先校验再匹配**：`job_data.py` 检查必需字段、类型、枚举和重复 ID；`job_matching.py` 只比较相同的 `skill_id`。这样状态有可复查的输入和规则，但输入证据本身仍需由人核实。
2. **事实由 Python 生成**：`build_trusted_facts` 再核对证据技能、层级、验证状态、关联 ID 与匹配状态，避免把模型自由文本放进可信事实字段。模型建议仍可能包含错误。
3. **客户端范围固定**：原 `/analyses` 只接受用户名和岗位 ID，服务端指定数据文件。V1.6 页面通过 `/demo/analyses` 只提交白名单案例 ID，复用相同规则函数而不是原接口；历史资料通过 `/demo/profile` 独立读取。API 默认不调用模型，也没有身份验证，只能按 README 用本机脱敏数据演示。
4. **评估保留失败信息**：固定案例使用模型响应替身；运行异常记录为失败，指标按适用案例计数。报告显示自由文本虚构声明在 4 个适用案例中有 3 个被接受，所以不能把案例通过数写成模型质量分数。
5. **私有输入与原演示隔离**：V1.7 不给原 API 增加私人文件默认值，而是单独启动本机服务，由启动调用者指定手工脱敏 JSON。浏览器只提交快照标识，服务器拒绝路径及其他未约定字段；同一份资料用于输入、判定和核对。来源与验证标记仍是声明，学历等资格不参与技能匹配。
6. **安全拒绝，不改原文**：共用校验拒绝不可编码 Unicode 与危险终端控制字符，避免服务启动异常和终端显示被改写；正常中文、表情及换行保留。固定错误不回显资料或路径。服务的本机及同源检查不替代身份验证，同机进程仍可能访问，不能用于共享或公网环境。

## 一次问题修复案例

早期可信事实校验只凭证据 ID 或验证标记，可能忽略证据所属技能、能力层级与状态之间的不一致。后来 `build_trusted_facts` 增加了完整关系检查；评估预期值也改为从原始夹具和预设状态独立构造，避免生产函数自己验证自己。对应反例见 [`test_job_analysis_agent.py`](../test_job_analysis_agent.py) 的 `TrustedFactsTests` 和 [`test_job_analysis_evaluation.py`](../test_job_analysis_evaluation.py) 的共享错误检测测试。项目曾发现并修复这一评估可信度缺口；个人是否参与发现或修复、能否用第一人称介绍，须按本人实际经历另行核对。不能据此说“证明所有模型输出真实”。

## 约三分钟项目讲解稿

> CareerAgent 是一个面向求职学习场景的 Python 项目。它用脱敏岗位要求和候选人证据演示岗位分析：程序先验证数据结构，再按相同技能 ID 和证据层级计算四种匹配状态。比如已验证项目证据可得到 `matched`，只有未验证的相关证据则得到 `unverified`。
>
> 项目也包含一个受控的模型工具调用流程。模型可以请求限定的只读工具，并生成解释、学习任务和面试问题；Python 负责执行范围检查、计算匹配状态、核对证据 ID，再把模型文字标记为未验证建议。对于学习进度更新，程序会先展示参数提案，只有用户输入精确的 `CONFIRM` 才写入并回读。
>
> 有一次评估可信度问题很典型：如果预期结果直接调用生产可信事实函数，生产函数出错时，测试也可能跟着得出同样的错误结果。项目后来改成从原始夹具独立构造预期值，并增加错误证据和错误状态的反例测试。
>
> 为便于复现，仓库提供了固定脱敏案例、离线评估和本地只读 API。API 可以无密钥运行，返回 Python 的确定性匹配与 `trusted_facts`。离线报告覆盖 26 个固定案例，同时也暴露了局限：4 个适用自由文本案例中，3 个虚构声明被接受；已知声明没有进入可信事实字段，并不表示模型不再幻觉。项目目前只适合本机脱敏演示，没有身份验证，也没有验证任意 JD 的准确率。
>
> V1.7 另外提供独立的本机私有入口，明确读取手工脱敏 JSON，用同一份资料展示岗位要求、来源、全部证据和分析结果。它不自动解析简历或核实能力，资格声明也不会自动转成录用结论；个人资料不放进公开演示或测试。

上面是项目讲解素材。实际面试时，第一人称参与方式需要与本人真实工作和学习过程一致。

## 面试时应能回答的关键问题

**为什么让 Python 决定匹配状态？** 因为状态由结构化 `skill_id`、证据层级和 `verified` 值按明确规则计算，能用相同输入复现；模型负责解释和建议，不修改状态或证据 ID。对应实现见 [`job_matching.py`](../job_matching.py)。

**`matched` 与 `unverified` 有什么区别？** 相同技能下存在已验证的 `project` 或 `production` 证据时为 `matched`；仅有未验证的相关证据时为 `unverified`。已验证的 `learning` 或 `practice` 证据是 `partial`，没有相关证据是 `missing`。这里的“已验证”是输入数据标记，不是系统自动鉴定真实能力。

**`trusted_facts` 能保证没有幻觉吗？** 不能。它限制可信字段只由 Python 根据结构化证据生成。模型自由文本仍可能出现虚构；离线报告中的 `3/4` 就是明确的反例。

**为什么 API 不能直接用于公网？** 它没有身份验证，数据范围和运行方式只为本机脱敏演示设计。请求不能指定任意路径，属于范围控制，并不能替代身份验证与生产安全设计。

**怎样复现核心结果？** 按 [`README.md`](../README.md) 安装依赖并启动监听 `127.0.0.1` 的 API，使用示例用户名与岗位 ID 请求 `/analyses`，对比[脱敏响应](../examples/careeragent_v1_3_api_analysis_output.json)；再运行完整单元测试和固定案例评估。API 复现不需要模型密钥。

**V1.7 接入真实资料了吗？** 可以读取由本机调用者手工整理、脱敏的真实来源声明，但没有自动 PDF 解析、语义技能映射或现实能力核实。公开测试只用人工资料，复现私有入口需按 [`PRIVATE_CASES.md`](PRIVATE_CASES.md) 自备 JSON；运行成功和预设核对不代表招聘通过。
