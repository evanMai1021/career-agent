import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main as main_module
from main import (
    generate_advice,
    get_study_progress,
    resolve_update_proposal,
    run_agent_loop,
    update_study_progress,
    validate_study_progress_update,
    validate_user_profile
)
from qwen_agent import run_qwen_agent_loop, run_qwen_update_proposal


SAMPLE_REVIEW_TASKS = [
    {
        "problem_id": "560",
        "title": "和为K的子数组",
        "topic": "前缀和与哈希表"
    },
    {
        "problem_id": "283",
        "title": "移动零",
        "topic": "双指针"
    }
]


def make_qwen_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=5):
    """创建不访问网络的千问响应替身。"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
    )


class GenerateAdviceTests(unittest.TestCase):
    """验证不同资料组合会得到准确、完整的三类建议。"""

    def test_two_rules_can_trigger_together(self):
        """Agent 未完成且题型为滑动窗口时，两条规则可以同时触发。"""
        user_profile = {
            "agent_progress": "尚未完成第一个版本",
            "leetcode_topic": "滑动窗口",
            "python_progress": "已完成Python基础"
        }

        advices = generate_advice(user_profile)

        self.assertEqual(
            advices,
            {
                "agent": {
                    "task": "跑通CareerAgent的JSON输入与结构化建议输出。",
                    "reason": (
                        "当前资料显示尚未完成第一个可运行版本，"
                        "应先形成可以实际运行的最小闭环。"
                    )
                },
                "leetcode": {
                    "task": "继续完成最小覆盖子串。",
                    "reason": "当前算法专题为滑动窗口。"
                },
                "python": {
                    "task": "继续按照当前Python计划学习。",
                    "reason": "当前学习进度未触发更具体的Python建议。"
                }
            }
        )

    def test_only_leetcode_rule(self):
        """只有滑动窗口条件满足时，仅替换 LeetCode 默认建议。"""
        user_profile = {
            "agent_progress": "已经完成第一个版本",
            "leetcode_topic": "滑动窗口",
            "python_progress": "已完成Python基础"
        }

        advices = generate_advice(user_profile)

        self.assertEqual(
            advices,
            {
                "agent": {
                    "task": "继续推进CareerAgent项目。",
                    "reason": "当前资料未触发更具体的Agent项目建议。"
                },
                "leetcode": {
                    "task": "继续完成最小覆盖子串。",
                    "reason": "当前算法专题为滑动窗口。"
                },
                "python": {
                    "task": "继续按照当前Python计划学习。",
                    "reason": "当前学习进度未触发更具体的Python建议。"
                }
            }
        )

    def test_default_advice(self):
        """没有具体规则触发时，三类建议仍保持完整。"""
        user_profile = {
            "agent_progress": "已经完成第一个版本",
            "leetcode_topic": "哈希表",
            "python_progress": "已完成Python基础"
        }

        advices = generate_advice(user_profile)

        self.assertEqual(
            advices,
            {
                "agent": {
                    "task": "继续推进CareerAgent项目。",
                    "reason": "当前资料未触发更具体的Agent项目建议。"
                },
                "leetcode": {
                    "task": "继续按照当前算法计划练习。",
                    "reason": "当前学习进度未触发更具体的LeetCode建议。"
                },
                "python": {
                    "task": "继续按照当前Python计划学习。",
                    "reason": "当前学习进度未触发更具体的Python建议。"
                }
            }
        )

    def test_only_python_rule(self):
        """Python 进度包含 JSON 时，仅替换 Python 默认建议。"""
        user_profile = {
            "agent_progress": "已经完成第一个版本",
            "leetcode_topic": "哈希表",
            "python_progress": "正在学习JSON"
        }

        advices = generate_advice(user_profile)

        self.assertEqual(
            advices,
            {
                "agent": {
                    "task": "继续推进CareerAgent项目。",
                    "reason": "当前资料未触发更具体的Agent项目建议。"
                },
                "leetcode": {
                    "task": "继续按照当前算法计划练习。",
                    "reason": "当前学习进度未触发更具体的LeetCode建议。"
                },
                "python": {
                    "task": "闭卷完成一次JSON读取、修改、保存和重新加载。",
                    "reason": "当前Python学习进度包含JSON，需要巩固完整数据处理流程。"
                }
            }
        )


class ValidateUserProfileTests(unittest.TestCase):
    """直接测试 validate_user_profile() 的四条关键验证路径。"""

    def test_valid_profile(self):
        """结构和字段全部正确时，验证函数正常返回 None。"""
        user_profile = {
            "target_role": "AI Agent开发"
        }

        self.assertIsNone(validate_user_profile(user_profile))

    def test_profile_must_be_dict(self):
        """列表不是合法的单用户资料，必须被拦截。"""
        output = StringIO()

        # 捕获错误提示，同时确认函数确实使用 SystemExit 终止流程。
        with redirect_stdout(output), self.assertRaises(SystemExit):
            validate_user_profile([])

        self.assertEqual(output.getvalue().strip(), "用户资料必须是对象")

    def test_missing_target_role(self):
        """缺少必要字段 target_role 时，返回对应的清晰提示。"""
        user_profile = {
            "python_progress": "JSON",
            "leetcode_topic": "滑动窗口",
            "agent_progress": "V0完成"
        }
        output = StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit):
            validate_user_profile(user_profile)

        self.assertEqual(
            output.getvalue().strip(),
            "用户资料缺少必要字段：target_role"
        )

    def test_target_role_must_be_string(self):
        """target_role 不是字符串时，资料不能进入建议生成过程。"""
        user_profile = {
            "target_role": 123,
            "python_progress": "JSON",
            "leetcode_topic": "滑动窗口",
            "agent_progress": "V0完成"
        }
        output = StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit):
            validate_user_profile(user_profile)

        self.assertEqual(
            output.getvalue().strip(),
            "用户资料字段必须是字符串：target_role"
        )


class GetStudyProgressTests(unittest.TestCase):
    """直接验证学习进度工具的成功路径和四种错误路径。"""

    def test_returns_progress_for_existing_user(self):
        """正常用户名会返回结构化、可序列化的学习进度。"""
        fixture = {
            "test_user": {
                "python_progress": "在CareerAgent中学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "测试用进度",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        progress_file = Path(temp_dir.name) / "progress.json"
        progress_file.write_text(
            json.dumps(fixture, ensure_ascii=False),
            encoding="utf-8"
        )

        result = get_study_progress(" test_user ", progress_file)

        self.assertEqual(
            result,
            {
                "ok": True,
                "username": "test_user",
                "progress": {
                    "python_progress": "在CareerAgent中学习函数与测试",
                    "leetcode_topic": "滑动窗口",
                    "agent_progress": "测试用进度",
                    "review_tasks": SAMPLE_REVIEW_TASKS
                }
            }
        )
        # json.dumps() 成功说明结果能交给后续模型或其他程序处理。
        self.assertIsInstance(json.dumps(result, ensure_ascii=False), str)

    def test_returns_error_for_unknown_user(self):
        """不存在的用户名不会触发 KeyError。"""
        progress_file = Path(__file__).with_name("study_progress.json")

        result = get_study_progress("missing_user", progress_file)

        self.assertEqual(
            result,
            {"ok": False, "error": "未找到用户：missing_user"}
        )

    def test_returns_error_when_file_is_missing(self):
        """文件不存在时返回错误字典，不向外抛出异常。"""
        with TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.json"

            result = get_study_progress("test_user", missing_file)

        self.assertFalse(result["ok"])
        self.assertIn("无法加载学习进度数据", result["error"])

    def test_returns_error_when_json_is_broken(self):
        """JSON 损坏时返回错误字典，不向外抛出解析异常。"""
        with TemporaryDirectory() as temp_dir:
            broken_file = Path(temp_dir) / "broken.json"
            broken_file.write_text("{", encoding="utf-8")

            result = get_study_progress("test_user", broken_file)

        self.assertFalse(result["ok"])
        self.assertIn("无法加载学习进度数据", result["error"])

    def test_returns_error_for_invalid_user_profile(self):
        """用户资料不是字典时，工具给出结构错误而不是继续读取字段。"""
        with TemporaryDirectory() as temp_dir:
            progress_file = Path(temp_dir) / "progress.json"
            progress_file.write_text(
                json.dumps({"test_user": []}, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_study_progress("test_user", progress_file)

        self.assertEqual(
            result,
            {"ok": False, "error": "用户学习进度必须是对象。"}
        )

    def test_rejects_legacy_string_review_tasks(self):
        """旧版题号字符串列表会被拦截，避免模型继续猜测题型。"""
        with TemporaryDirectory() as temp_dir:
            progress_file = Path(temp_dir) / "progress.json"
            progress_file.write_text(
                json.dumps({
                    "test_user": {
                        "python_progress": "学习函数与测试",
                        "leetcode_topic": "滑动窗口",
                        "agent_progress": "CareerAgent V0.5完成",
                        "review_tasks": ["560"]
                    }
                }, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_study_progress("test_user", progress_file)

        self.assertEqual(
            result,
            {"ok": False, "error": "第1项复习任务必须是对象。"}
        )

    def test_rejects_review_task_with_missing_topic(self):
        """缺少专题的复习任务不能交给模型。"""
        with TemporaryDirectory() as temp_dir:
            progress_file = Path(temp_dir) / "progress.json"
            progress_file.write_text(
                json.dumps({
                    "test_user": {
                        "python_progress": "学习函数与测试",
                        "leetcode_topic": "滑动窗口",
                        "agent_progress": "CareerAgent V0.5完成",
                        "review_tasks": [{
                            "problem_id": "560",
                            "title": "和为K的子数组"
                        }]
                    }
                }, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_study_progress("test_user", progress_file)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": (
                    "第1项复习任务必须且只能包含字段："
                    "problem_id、title、topic。"
                )
            }
        )

    def test_rejects_empty_review_task_topic(self):
        """专题字段虽然是字符串，但空白内容仍然不合格。"""
        with TemporaryDirectory() as temp_dir:
            progress_file = Path(temp_dir) / "progress.json"
            progress_file.write_text(
                json.dumps({
                    "test_user": {
                        "python_progress": "学习函数与测试",
                        "leetcode_topic": "滑动窗口",
                        "agent_progress": "CareerAgent V0.5完成",
                        "review_tasks": [{
                            "problem_id": "560",
                            "title": "和为K的子数组",
                            "topic": "   "
                        }]
                    }
                }, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_study_progress("test_user", progress_file)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "第1项复习任务字段必须是非空字符串：topic"
            }
        )


class UpdateStudyProgressTests(unittest.TestCase):
    """验证第二个工具只更新合法字段并保存到本地 JSON。"""

    def setUp(self):
        """每项测试都使用临时文件，避免修改项目演示数据。"""
        self.temp_dir = TemporaryDirectory()
        self.progress_file = Path(self.temp_dir.name) / "progress.json"
        self.original_data = {
            "test_user": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.2完成",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }
        self.progress_file.write_text(
            json.dumps(self.original_data, ensure_ascii=False),
            encoding="utf-8"
        )

    def tearDown(self):
        """由临时目录负责清理本项测试产生的数据。"""
        self.temp_dir.cleanup()

    def test_updates_and_saves_allowed_field(self):
        """合法字段会更新，重新加载文件也能读到新值。"""
        result = update_study_progress(
            "test_user",
            "agent_progress",
            "CareerAgent V0.3完成",
            self.progress_file
        )

        saved_data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["updated_field"], "agent_progress")
        self.assertEqual(
            saved_data["test_user"]["agent_progress"],
            "CareerAgent V0.3完成"
        )

    def test_rejects_unknown_field_without_changing_file(self):
        """白名单外字段被拒绝，原文件内容保持不变。"""
        result = update_study_progress(
            "test_user",
            "target_role",
            "Python开发",
            self.progress_file
        )

        saved_data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        self.assertFalse(result["ok"])
        self.assertEqual(saved_data, self.original_data)

    def test_rejects_wrong_value_type(self):
        """文本进度字段不能写入整数。"""
        result = update_study_progress(
            "test_user",
            "python_progress",
            123,
            self.progress_file
        )

        self.assertEqual(
            result,
            {"ok": False, "error": "学习进度字段必须是字符串：python_progress"}
        )

    def test_returns_error_for_unknown_user(self):
        """不存在的用户不会被写入文件。"""
        result = update_study_progress(
            "missing_user",
            "agent_progress",
            "新进度",
            self.progress_file
        )

        self.assertEqual(
            result,
            {"ok": False, "error": "未找到用户：missing_user"}
        )

    def test_updates_structured_review_tasks(self):
        """合法的题号、题名和专题字典列表可以保存。"""
        new_tasks = [{
            "problem_id": "76",
            "title": "最小覆盖子串",
            "topic": "滑动窗口"
        }]

        result = update_study_progress(
            "test_user",
            "review_tasks",
            new_tasks,
            self.progress_file
        )

        saved_data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(saved_data["test_user"]["review_tasks"], new_tasks)

    def test_rejects_malformed_review_tasks_without_changing_file(self):
        """缺少专题的写入值会被拒绝，原文件保持不变。"""
        invalid_tasks = [{
            "problem_id": "76",
            "title": "最小覆盖子串"
        }]

        result = update_study_progress(
            "test_user",
            "review_tasks",
            invalid_tasks,
            self.progress_file
        )

        saved_data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        self.assertFalse(result["ok"])
        self.assertEqual(saved_data, self.original_data)


class ResolveUpdateProposalTests(unittest.TestCase):
    """验证只有明确确认后才会执行写入工具。"""

    def setUp(self):
        self.proposal = {
            "username": "test_user",
            "field": "agent_progress",
            "new_value": "CareerAgent V0.7确认流程"
        }

    def test_rejection_does_not_execute_update_tool(self):
        """任何非 CONFIRM 输入都取消，写入工具不得被调用。"""
        update_tool = MagicMock()

        result = resolve_update_proposal(
            self.proposal,
            "no",
            "progress.json",
            update_tool=update_tool
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["used_tools"], [])
        self.assertEqual(result["stop_reason"], "user_cancelled")
        update_tool.assert_not_called()

    def test_confirmation_executes_update_tool(self):
        """精确输入 CONFIRM 后，才把已预览参数交给写入工具。"""
        update_tool = MagicMock(return_value={
            "ok": True,
            "updated_field": "agent_progress",
            "progress": {
                "agent_progress": "CareerAgent V0.7确认流程"
            }
        })

        result = resolve_update_proposal(
            self.proposal,
            "CONFIRM",
            "progress.json",
            update_tool=update_tool
        )

        update_tool.assert_called_once_with(
            "test_user",
            "agent_progress",
            "CareerAgent V0.7确认流程",
            "progress.json"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["used_tools"], ["update_study_progress"])
        self.assertEqual(result["stop_reason"], "completed")

    def test_write_failure_is_reported_after_tool_execution(self):
        """写入失败会停止并说明工具已尝试执行，而不是假装没调用。"""
        update_tool = MagicMock(return_value={
            "ok": False,
            "error": "无法保存学习进度数据。"
        })

        result = resolve_update_proposal(
            self.proposal,
            "CONFIRM",
            "progress.json",
            update_tool=update_tool
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "update_failed")
        self.assertEqual(result["stop_reason"], "tool_error")
        self.assertEqual(result["used_tools"], ["update_study_progress"])
        self.assertEqual(result["error"], "无法保存学习进度数据。")

    def test_confirmation_updates_a_temporary_json_file(self):
        """确认流程与真实写入工具组合后，临时JSON会保存新值。"""
        original_data = {
            "test_user": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.6完成",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }
        with TemporaryDirectory() as temp_dir:
            progress_file = Path(temp_dir) / "progress.json"
            progress_file.write_text(
                json.dumps(original_data, ensure_ascii=False),
                encoding="utf-8"
            )

            result = resolve_update_proposal(
                self.proposal,
                "CONFIRM",
                progress_file
            )

            saved_data = json.loads(progress_file.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            saved_data["test_user"]["agent_progress"],
            "CareerAgent V0.7确认流程"
        )


class ControlledAgentLoopTests(unittest.TestCase):
    """验证规则版循环能完成、遇错停止并遵守最大步数。"""

    def test_completes_read_and_advice_steps(self):
        """正常数据经过读取和建议两步后主动结束。"""
        tool_result = {
            "ok": True,
            "username": "test_user",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.3完成",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }

        with patch.object(
            main_module,
            "get_study_progress",
            return_value=tool_result
        ) as progress_tool:
            result = run_agent_loop("test_user", "progress.json")

        progress_tool.assert_called_once_with("test_user", "progress.json")
        self.assertTrue(result["ok"])
        self.assertEqual(result["used_tools"], ["get_study_progress"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "completed")
        self.assertEqual(
            [item["action"] for item in result["agent_loop"]["trace"]],
            ["get_study_progress", "generate_advice"]
        )

    def test_stops_when_tool_returns_error(self):
        """读取工具失败后不会继续生成建议。"""
        with patch.object(
            main_module,
            "get_study_progress",
            return_value={"ok": False, "error": "进度文件错误"}
        ):
            result = run_agent_loop("test_user", "progress.json")

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "tool_error")
        self.assertNotIn("advice", result)

    def test_stops_at_maximum_steps(self):
        """只有一步额度时，读取完成后按最大步数安全停止。"""
        tool_result = {
            "ok": True,
            "username": "test_user",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.3完成",
                "review_tasks": []
            }
        }

        with patch.object(
            main_module,
            "get_study_progress",
            return_value=tool_result
        ):
            result = run_agent_loop(
                "test_user",
                "progress.json",
                max_steps=1
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "max_steps_reached"
        )


class QwenAgentLoopTests(unittest.TestCase):
    """使用模型替身验证千问循环，不产生真实API费用。"""

    def test_model_calls_read_tool_then_returns_structured_advice(self):
        """模型先请求只读工具，再根据工具结果返回三类建议。"""
        tool_call = SimpleNamespace(
            id="call_001",
            function=SimpleNamespace(
                name="get_study_progress",
                arguments=json.dumps({"username": "test_user"})
            )
        )
        advice = {
            "python": {
                "task": "复习JSON读写。",
                "reason": "当前正在学习函数与测试。"
            },
            "leetcode": {
                "task": "完成一道滑动窗口题。",
                "reason": "当前专题是滑动窗口。"
            },
            "agent": {
                "task": "验证千问工具调用。",
                "reason": "当前CareerAgent正在接入LLM。"
            }
        }
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            make_qwen_response(tool_calls=[tool_call]),
            make_qwen_response(content=json.dumps(advice, ensure_ascii=False))
        ]
        progress_tool = MagicMock(return_value={
            "ok": True,
            "username": "test_user",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.4完成",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        })

        result = run_qwen_agent_loop(
            "test_user",
            "AI Agent开发",
            "progress.json",
            progress_tool,
            client=client
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["used_tools"], ["get_study_progress"])
        self.assertEqual(result["advice"], advice)
        self.assertEqual(result["agent_loop"]["mode"], "llm_tool_calling")
        self.assertEqual(result["agent_loop"]["stop_reason"], "completed")
        self.assertEqual(result["llm_usage"]["total_tokens"], 30)
        progress_tool.assert_called_once_with("test_user", "progress.json")
        first_request = client.chat.completions.create.call_args_list[0].kwargs
        self.assertEqual(first_request["tool_choice"], "auto")
        self.assertNotIn("response_format", first_request)
        second_request = client.chat.completions.create.call_args_list[1].kwargs
        self.assertNotIn("tools", second_request)
        self.assertEqual(second_request["response_format"]["type"], "json_schema")

    def test_rejects_tool_request_for_another_user(self):
        """模型不能绕过当前用户范围读取另一名用户。"""
        tool_call = SimpleNamespace(
            id="call_002",
            function=SimpleNamespace(
                name="get_study_progress",
                arguments=json.dumps({"username": "other_user"})
            )
        )
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            tool_calls=[tool_call]
        )
        progress_tool = MagicMock()

        result = run_qwen_agent_loop(
            "test_user",
            "AI Agent开发",
            "progress.json",
            progress_tool,
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "tool_scope_violation"
        )
        progress_tool.assert_not_called()

    def test_rejects_invalid_structured_output(self):
        """缺少三类建议的模型响应不能进入最终结果。"""
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            content=json.dumps({"python": "继续学习"}, ensure_ascii=False)
        )

        result = run_qwen_agent_loop(
            "test_user",
            "AI Agent开发",
            "progress.json",
            MagicMock(),
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "invalid_model_output"
        )

    def test_stops_when_model_repeats_tool_until_limit(self):
        """即使模型重复调用工具，也会被最大步数终止。"""
        tool_call = SimpleNamespace(
            id="call_003",
            function=SimpleNamespace(
                name="get_study_progress",
                arguments=json.dumps({"username": "test_user"})
            )
        )
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            tool_calls=[tool_call]
        )
        progress_tool = MagicMock(return_value={
            "ok": True,
            "username": "test_user",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.4完成",
                "review_tasks": []
            }
        })

        result = run_qwen_agent_loop(
            "test_user",
            "AI Agent开发",
            "progress.json",
            progress_tool,
            max_steps=1,
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "max_steps_reached"
        )


class QwenUpdateProposalTests(unittest.TestCase):
    """验证模型只能提出写入参数，不能在确认前修改文件。"""

    def test_returns_validated_proposal_without_executing_tool(self):
        """合法参数会进入待确认状态，但 used_tools 仍为空。"""
        tool_call = SimpleNamespace(
            id="call_update_001",
            function=SimpleNamespace(
                name="update_study_progress",
                arguments=json.dumps({
                    "username": "test_user",
                    "field": "agent_progress",
                    "new_value": "CareerAgent V0.7提案阶段"
                }, ensure_ascii=False)
            )
        )
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            tool_calls=[tool_call]
        )
        validator = MagicMock(return_value=None)

        result = run_qwen_update_proposal(
            "test_user",
            "AI Agent开发",
            "把Agent进度更新为CareerAgent V0.7提案阶段",
            validator,
            client=client
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["used_tools"], [])
        self.assertEqual(result["requested_tools"], ["update_study_progress"])
        self.assertEqual(
            result["write_proposal"],
            {
                "username": "test_user",
                "field": "agent_progress",
                "new_value": "CareerAgent V0.7提案阶段"
            }
        )
        validator.assert_called_once_with(
            "agent_progress",
            "CareerAgent V0.7提案阶段"
        )
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            "update_study_progress"
        )

    def test_rejects_proposal_for_another_user(self):
        """模型不能提出修改另一名用户的进度。"""
        tool_call = SimpleNamespace(
            id="call_update_002",
            function=SimpleNamespace(
                name="update_study_progress",
                arguments=json.dumps({
                    "username": "other_user",
                    "field": "agent_progress",
                    "new_value": "不应接受"
                }, ensure_ascii=False)
            )
        )
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            tool_calls=[tool_call]
        )
        validator = MagicMock()

        result = run_qwen_update_proposal(
            "test_user",
            "AI Agent开发",
            "更新进度",
            validator,
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "tool_scope_violation"
        )
        validator.assert_not_called()

    def test_rejects_invalid_update_value(self):
        """Python验证未通过时，模型提案不能进入待确认状态。"""
        tool_call = SimpleNamespace(
            id="call_update_003",
            function=SimpleNamespace(
                name="update_study_progress",
                arguments=json.dumps({
                    "username": "test_user",
                    "field": "review_tasks",
                    "new_value": "560"
                }, ensure_ascii=False)
            )
        )
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            tool_calls=[tool_call]
        )

        result = run_qwen_update_proposal(
            "test_user",
            "AI Agent开发",
            "把复习任务更新为560",
            validate_study_progress_update,
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "invalid_update_proposal"
        )
        self.assertEqual(result["used_tools"], [])

    def test_rejects_missing_tool_proposal(self):
        """模型没有返回唯一工具调用时，不能猜测写入参数。"""
        client = MagicMock()
        client.chat.completions.create.return_value = make_qwen_response(
            content="我建议更新进度",
            tool_calls=[]
        )

        result = run_qwen_update_proposal(
            "test_user",
            "AI Agent开发",
            "更新Agent进度",
            validate_study_progress_update,
            client=client
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "invalid_model_output"
        )


class MainFlowTests(unittest.TestCase):
    """验证主流程能在规则模式和千问模式之间受控切换。"""

    def test_main_calls_tool_and_records_it(self):
        """工具返回的滑动窗口专题会生成带原因的对应建议。"""
        users = {"test_user": {"target_role": "AI Agent开发"}}
        tool_result = {
            "ok": True,
            "username": "test_user",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0完成",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }
        output = StringIO()

        with (
            patch.object(main_module, "load_users", return_value=users),
            patch.object(
                main_module,
                "get_study_progress",
                return_value=tool_result
            ) as progress_tool,
            patch.dict("os.environ", {"CAREER_AGENT_MODE": "rule"}),
            patch("builtins.input", side_effect=["test_user", ""]),
            redirect_stdout(output)
        ):
            main_module.main()

        progress_tool.assert_called_once_with("test_user", "study_progress.json")
        result = json.loads(output.getvalue())
        self.assertEqual(result["used_tools"], ["get_study_progress"])
        self.assertEqual(
            result["advice"]["leetcode"],
            {
                "task": "继续完成最小覆盖子串。",
                "reason": "当前算法专题为滑动窗口。"
            }
        )

    def test_main_uses_qwen_loop_in_llm_mode(self):
        """LLM模式由主流程调用千问循环，并保留模型与用量记录。"""
        users = {"test_user": {"target_role": "AI Agent开发"}}
        loop_result = {
            "ok": True,
            "used_tools": ["get_study_progress"],
            "model": "qwen3.8-flash",
            "llm_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            },
            "agent_loop": {
                "mode": "llm_tool_calling",
                "max_steps": 3,
                "stop_reason": "completed",
                "trace": []
            },
            "advice": {
                category: {"task": "测试任务", "reason": "测试原因"}
                for category in ("python", "leetcode", "agent")
            }
        }
        output = StringIO()

        with (
            patch.object(main_module, "load_users", return_value=users),
            patch.object(
                main_module,
                "run_qwen_agent_loop",
                return_value=loop_result
            ) as qwen_loop,
            patch.dict("os.environ", {"CAREER_AGENT_MODE": "llm"}),
            patch("builtins.input", side_effect=["test_user", ""]),
            redirect_stdout(output)
        ):
            main_module.main()

        qwen_loop.assert_called_once_with(
            username="test_user",
            target_role="AI Agent开发",
            progress_file="study_progress.json",
            get_progress_tool=main_module.get_study_progress
        )
        result = json.loads(output.getvalue())
        self.assertEqual(result["model"], "qwen3.8-flash")
        self.assertEqual(result["llm_usage"]["total_tokens"], 150)
        self.assertEqual(result["agent_loop"]["mode"], "llm_tool_calling")

    def test_main_cancels_update_without_exact_confirmation(self):
        """主流程展示提案后，空确认会取消且不执行写入。"""
        users = {"test_user": {"target_role": "AI Agent开发"}}
        proposal_result = {
            "ok": True,
            "status": "confirmation_required",
            "used_tools": [],
            "requested_tools": ["update_study_progress"],
            "model": "qwen3.8-flash",
            "llm_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100
            },
            "write_proposal": {
                "username": "test_user",
                "field": "agent_progress",
                "new_value": "CareerAgent V0.7提案阶段"
            },
            "agent_loop": {
                "mode": "llm_update_proposal",
                "max_steps": 1,
                "stop_reason": "confirmation_required",
                "trace": []
            }
        }
        output = StringIO()

        with (
            patch.object(main_module, "load_users", return_value=users),
            patch.object(
                main_module,
                "run_qwen_update_proposal",
                return_value=proposal_result
            ) as proposal_call,
            patch.object(main_module, "update_study_progress") as update_tool,
            patch.dict("os.environ", {"CAREER_AGENT_MODE": "llm"}),
            patch(
                "builtins.input",
                side_effect=[
                    "test_user",
                    "update",
                    "把Agent进度更新为CareerAgent V0.7提案阶段",
                    ""
                ]
            ),
            redirect_stdout(output)
        ):
            main_module.main()

        proposal_call.assert_called_once_with(
            username="test_user",
            target_role="AI Agent开发",
            user_request="把Agent进度更新为CareerAgent V0.7提案阶段",
            validate_update=main_module.validate_study_progress_update
        )
        update_tool.assert_not_called()
        final_output = output.getvalue().split("最终结果：", maxsplit=1)[1]
        result = json.loads(final_output)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["used_tools"], [])
        self.assertEqual(result["requested_tools"], ["update_study_progress"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "user_cancelled"
        )

    def test_main_executes_update_after_exact_confirmation(self):
        """主流程收到 CONFIRM 后执行写入并记录完整轨迹。"""
        users = {"test_user": {"target_role": "AI Agent开发"}}
        proposal_result = {
            "ok": True,
            "status": "confirmation_required",
            "used_tools": [],
            "requested_tools": ["update_study_progress"],
            "model": "qwen3.8-flash",
            "llm_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100
            },
            "write_proposal": {
                "username": "test_user",
                "field": "agent_progress",
                "new_value": "CareerAgent V0.7确认流程"
            },
            "agent_loop": {
                "mode": "llm_update_proposal",
                "max_steps": 1,
                "stop_reason": "confirmation_required",
                "trace": [{
                    "step": 1,
                    "action": "qwen_update_proposal",
                    "status": "confirmation_required"
                }]
            }
        }
        update_result = {
            "ok": True,
            "username": "test_user",
            "updated_field": "agent_progress",
            "progress": {
                "python_progress": "学习函数与测试",
                "leetcode_topic": "滑动窗口",
                "agent_progress": "CareerAgent V0.7确认流程",
                "review_tasks": SAMPLE_REVIEW_TASKS
            }
        }
        output = StringIO()

        with (
            patch.object(main_module, "load_users", return_value=users),
            patch.object(
                main_module,
                "run_qwen_update_proposal",
                return_value=proposal_result
            ),
            patch.object(
                main_module,
                "update_study_progress",
                return_value=update_result
            ) as update_tool,
            patch.dict("os.environ", {"CAREER_AGENT_MODE": "llm"}),
            patch(
                "builtins.input",
                side_effect=[
                    "test_user",
                    "update",
                    "更新Agent进度",
                    "CONFIRM"
                ]
            ),
            redirect_stdout(output)
        ):
            main_module.main()

        update_tool.assert_called_once_with(
            "test_user",
            "agent_progress",
            "CareerAgent V0.7确认流程",
            "study_progress.json"
        )
        final_output = output.getvalue().split("最终结果：", maxsplit=1)[1]
        result = json.loads(final_output)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["used_tools"], ["update_study_progress"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "completed")
        self.assertEqual(
            [item["action"] for item in result["agent_loop"]["trace"]],
            [
                "qwen_update_proposal",
                "user_confirmation",
                "update_study_progress"
            ]
        )


if __name__ == "__main__":
    unittest.main()
