import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from job_analysis_agent import run_job_analysis_agent
from job_matching import get_candidate_evidence, get_job_requirements
from main import get_study_progress


JOB_RESULT = {
    "ok": True,
    "job_id": "demo_ai_agent_intern",
    "title": "AI Agent 实习生",
    "requirements": [
        {
            "requirement_id": "req_python",
            "skill_id": "python",
            "description": "能够使用 Python 完成功能开发",
            "category": "required",
            "priority": 1
        },
        {
            "requirement_id": "req_agent",
            "skill_id": "agent_tool_calling",
            "description": "理解 Agent 工具调用",
            "category": "required",
            "priority": 2
        },
        {
            "requirement_id": "req_fastapi",
            "skill_id": "fastapi",
            "description": "了解 FastAPI",
            "category": "preferred",
            "priority": 3
        }
    ]
}

EVIDENCE_RESULT = {
    "ok": True,
    "username": "test_user",
    "evidence": [
        {
            "evidence_id": "ev_python_project",
            "skill_id": "python",
            "description": "完成 CareerAgent Python 项目",
            "level": "project",
            "source": "CareerAgent",
            "verified": True
        },
        {
            "evidence_id": "ev_agent_practice",
            "skill_id": "agent_tool_calling",
            "description": "完成工具调用练习",
            "level": "practice",
            "source": "CareerAgent",
            "verified": True
        },
        {
            "evidence_id": "ev_fastapi_learning",
            "skill_id": "fastapi",
            "description": "FastAPI 学习记录",
            "level": "learning",
            "source": "本地脱敏学习记录",
            "verified": False
        }
    ]
}

PROGRESS = {
    "python_progress": "正在复习函数、JSON 与单元测试",
    "leetcode_topic": "滑动窗口",
    "agent_progress": "CareerAgent V0.9b 已完成",
    "review_tasks": []
}

EXPECTED_MATCHES = [
    {
        **JOB_RESULT["requirements"][0],
        "status": "matched",
        "related_evidence_ids": ["ev_python_project"]
    },
    {
        **JOB_RESULT["requirements"][1],
        "status": "partial",
        "related_evidence_ids": ["ev_agent_practice"]
    },
    {
        **JOB_RESULT["requirements"][2],
        "status": "unverified",
        "related_evidence_ids": ["ev_fastapi_learning"]
    }
]


def make_tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False)
        )
    )


def make_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls or []
        ))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
    )


def make_valid_analysis():
    return {
        "match_explanations": [
            {
                "requirement_id": "req_python",
                "status": "matched",
                "related_evidence_ids": ["ev_python_project"],
                "summary": "存在已验证的项目级 Python 证据。"
            },
            {
                "requirement_id": "req_agent",
                "status": "partial",
                "related_evidence_ids": ["ev_agent_practice"],
                "summary": "已有练习证据，但尚未达到项目级。"
            },
            {
                "requirement_id": "req_fastapi",
                "status": "unverified",
                "related_evidence_ids": ["ev_fastapi_learning"],
                "summary": "存在学习描述，但证据尚未验证。"
            }
        ],
        "learning_tasks": [
            {
                "requirement_id": "req_agent",
                "task": "在现有项目中解释一次完整工具调用流程。"
            },
            {
                "requirement_id": "req_fastapi",
                "task": "完成一个本地 FastAPI 最小接口练习。"
            }
        ],
        "interview_questions": [
            {
                "requirement_id": "req_python",
                "question": "你如何验证 Python 项目没有修改真实数据？"
            },
            {
                "requirement_id": "req_agent",
                "question": "Agent 工具调用中谁负责权限校验？"
            },
            {
                "requirement_id": "req_fastapi",
                "question": "你会如何设计一个只读接口？"
            }
        ],
        "study_progress_source": copy.deepcopy(PROGRESS)
    }


class JobAnalysisAgentTests(unittest.TestCase):
    def setUp(self):
        self.job_tool = MagicMock(return_value=copy.deepcopy(JOB_RESULT))
        self.evidence_tool = MagicMock(return_value=copy.deepcopy(EVIDENCE_RESULT))
        self.progress_tool = MagicMock(return_value={
            "ok": True,
            "username": "test_user",
            "progress": copy.deepcopy(PROGRESS)
        })

    def run_agent(self, client, **overrides):
        arguments = {
            "username": "test_user",
            "job_id": "demo_ai_agent_intern",
            "jobs_file": "jobs.json",
            "evidence_file": "candidate_evidence.json",
            "progress_file": "study_progress.json",
            "get_job_tool": self.job_tool,
            "get_evidence_tool": self.evidence_tool,
            "get_progress_tool": self.progress_tool,
            "client": client
        }
        arguments.update(overrides)
        return run_job_analysis_agent(**arguments)

    def make_happy_client(self, analysis=None):
        if analysis is None:
            analysis = make_valid_analysis()
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            make_response(tool_calls=[make_tool_call(
                "call_job",
                "get_job_requirements",
                {"job_id": "demo_ai_agent_intern"}
            )]),
            make_response(tool_calls=[make_tool_call(
                "call_evidence",
                "get_candidate_evidence",
                {"username": "test_user"}
            )]),
            make_response(tool_calls=[make_tool_call(
                "call_progress",
                "get_study_progress",
                {"username": "test_user"}
            )]),
            make_response(content=json.dumps(analysis, ensure_ascii=False))
        ]
        return client

    def test_reads_three_scoped_tools_and_returns_python_matches(self):
        client = self.make_happy_client()

        result = self.run_agent(client)

        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"], EXPECTED_MATCHES)
        self.assertEqual(result["analysis"], make_valid_analysis())
        self.assertEqual(result["used_tools"], [
            "get_job_requirements",
            "get_candidate_evidence",
            "get_study_progress"
        ])
        self.assertEqual(result["agent_loop"]["stop_reason"], "completed")
        self.assertEqual(result["llm_usage"]["total_tokens"], 60)
        self.job_tool.assert_called_once_with(
            "demo_ai_agent_intern", "jobs.json"
        )
        self.evidence_tool.assert_called_once_with(
            "test_user", "candidate_evidence.json"
        )
        self.progress_tool.assert_called_once_with(
            "test_user", "study_progress.json"
        )

        for request in client.chat.completions.create.call_args_list[:3]:
            serialized_tools = json.dumps(request.kwargs["tools"])
            self.assertNotIn("jobs_file", serialized_tools)
            self.assertNotIn("evidence_file", serialized_tools)
            self.assertNotIn("progress_file", serialized_tools)
        final_request = client.chat.completions.create.call_args_list[3].kwargs
        self.assertNotIn("tools", final_request)
        self.assertEqual(final_request["response_format"]["type"], "json_schema")
        system_text = "".join(
            message["content"]
            for message in final_request["messages"]
            if message["role"] == "system"
        )
        self.assertIn("每个非matched要求恰好提供一项", system_text)
        self.assertIn("study_progress_source必须原样复制", system_text)

    def test_project_files_complete_offline_agent_flow_without_changes(self):
        project_root = Path(__file__).parent
        data_paths = [
            project_root / "jobs.json",
            project_root / "candidate_evidence.json",
            project_root / "study_progress.json"
        ]
        before = {path: path.read_bytes() for path in data_paths}
        progress_result = get_study_progress(
            "test_user", project_root / "study_progress.json"
        )
        analysis = {
            "match_explanations": [
                {
                    "requirement_id": "req_python",
                    "status": "matched",
                    "related_evidence_ids": ["ev_python_tests"],
                    "summary": "存在已验证的项目级 Python 测试证据。"
                },
                {
                    "requirement_id": "req_agent_tool_calling",
                    "status": "matched",
                    "related_evidence_ids": ["ev_agent_tool_calling"],
                    "summary": "存在已验证的项目级工具调用证据。"
                },
                {
                    "requirement_id": "req_fastapi",
                    "status": "unverified",
                    "related_evidence_ids": ["ev_fastapi_plan"],
                    "summary": "只有尚未验证的学习记录。"
                }
            ],
            "learning_tasks": [{
                "requirement_id": "req_fastapi",
                "task": "完成一个可测试的本地接口练习。"
            }],
            "interview_questions": [
                {
                    "requirement_id": "req_python",
                    "question": "如何证明测试没有改动真实数据？"
                },
                {
                    "requirement_id": "req_agent_tool_calling",
                    "question": "如何限制模型的工具权限？"
                },
                {
                    "requirement_id": "req_fastapi",
                    "question": "如何设计只读接口的输入校验？"
                }
            ],
            "study_progress_source": progress_result["progress"]
        }
        client = self.make_happy_client(analysis)

        result = run_job_analysis_agent(
            username="test_user",
            job_id="demo_ai_agent_intern",
            jobs_file=project_root / "jobs.json",
            evidence_file=project_root / "candidate_evidence.json",
            progress_file=project_root / "study_progress.json",
            get_job_tool=get_job_requirements,
            get_evidence_tool=get_candidate_evidence,
            get_progress_tool=get_study_progress,
            client=client
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            [match["status"] for match in result["matches"]],
            ["matched", "matched", "unverified"]
        )
        self.assertEqual(
            before,
            {path: path.read_bytes() for path in data_paths}
        )

    def test_saved_v1_example_matches_validated_project_result(self):
        project_root = Path(__file__).parent
        example = json.loads(
            (project_root / "examples" / "careeragent_v1_0_job_analysis_output.json")
            .read_text(encoding="utf-8")
        )
        client = self.make_happy_client(example["result"]["analysis"])

        result = run_job_analysis_agent(
            username="test_user",
            job_id="demo_ai_agent_intern",
            jobs_file=project_root / "jobs.json",
            evidence_file=project_root / "candidate_evidence.json",
            progress_file=project_root / "study_progress.json",
            get_job_tool=get_job_requirements,
            get_evidence_tool=get_candidate_evidence,
            get_progress_tool=get_study_progress,
            client=client
        )

        self.assertEqual(example["evidence_type"], "offline_model_stub")
        self.assertTrue(result["ok"])
        self.assertEqual(example["result"]["matches"], result["matches"])
        self.assertEqual(example["result"]["analysis"], result["analysis"])

    def test_rejects_cross_job_tool_request(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call(
                "call_other_job",
                "get_job_requirements",
                {"job_id": "other_job"}
            )
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "tool_scope_violation")
        self.job_tool.assert_not_called()

    def test_rejects_cross_user_tool_request(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call(
                "call_other_user",
                "get_candidate_evidence",
                {"username": "other_user"}
            )
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "tool_scope_violation")
        self.evidence_tool.assert_not_called()

    def test_rejects_unauthorized_tool(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call("call_write", "update_study_progress", {
                "username": "test_user"
            })
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "unauthorized_tool")
        self.progress_tool.assert_not_called()

    def test_rejects_tool_arguments_with_unapproved_file_path(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call(
                "call_path_override",
                "get_job_requirements",
                {
                    "job_id": "demo_ai_agent_intern",
                    "jobs_file": "other.json"
                }
            )
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "invalid_tool_arguments"
        )
        self.job_tool.assert_not_called()

    def test_rejects_tool_result_for_another_job(self):
        self.job_tool.return_value = {
            **copy.deepcopy(JOB_RESULT),
            "job_id": "other_job"
        }
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call(
                "call_wrong_job_result",
                "get_job_requirements",
                {"job_id": "demo_ai_agent_intern"}
            )
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["agent_loop"]["stop_reason"],
            "tool_scope_violation"
        )

    def test_rejects_response_that_changes_python_match_status(self):
        analysis = make_valid_analysis()
        analysis["match_explanations"][1]["status"] = "matched"

        result = self.run_agent(self.make_happy_client(analysis))

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "invalid_model_output")
        self.assertIn("status与Python结果不一致", result["error"])

    def test_rejects_fabricated_evidence_id(self):
        analysis = make_valid_analysis()
        analysis["match_explanations"][0]["related_evidence_ids"] = [
            "ev_not_real"
        ]

        result = self.run_agent(self.make_happy_client(analysis))

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "invalid_model_output")
        self.assertIn("related_evidence_ids", result["error"])

    def test_rejects_task_for_matched_requirement(self):
        analysis = make_valid_analysis()
        analysis["learning_tasks"].insert(0, {
            "requirement_id": "req_python",
            "task": "重复学习已经匹配的要求。"
        })

        result = self.run_agent(self.make_happy_client(analysis))

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "invalid_model_output")

    def test_rejects_final_response_before_required_tools(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(
            content=json.dumps(make_valid_analysis(), ensure_ascii=False)
        )

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "missing_required_tools")

    def test_stops_when_read_tool_returns_error(self):
        self.job_tool.return_value = {"ok": False, "error": "岗位数据损坏。"}
        client = MagicMock()
        client.chat.completions.create.return_value = make_response(tool_calls=[
            make_tool_call(
                "call_job_error",
                "get_job_requirements",
                {"job_id": "demo_ai_agent_intern"}
            )
        ])

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "岗位数据损坏。")
        self.assertEqual(result["agent_loop"]["stop_reason"], "tool_error")

    def test_model_error_keeps_local_matches_without_retrying_model(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = ConnectionError("offline")

        result = self.run_agent(client)

        self.assertFalse(result["ok"])
        self.assertEqual(result["agent_loop"]["stop_reason"], "model_error")
        self.assertEqual(result["matches"], EXPECTED_MATCHES)
        self.assertEqual(result["fallback"], {
            "mode": "python_deterministic_match",
            "available": True
        })
        self.assertEqual(result["used_tools"], [
            "get_job_requirements",
            "get_candidate_evidence"
        ])
        self.progress_tool.assert_not_called()
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(
            [item["step"] for item in result["agent_loop"]["trace"]],
            [1, 2, 3, 4]
        )

    def test_rejects_invalid_max_steps_before_model_call(self):
        client = MagicMock()

        result = self.run_agent(client, max_steps=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "max_steps必须是至少4的整数。")
        client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
