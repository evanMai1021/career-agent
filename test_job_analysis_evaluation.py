import copy
import json
import unittest
from pathlib import Path

from job_analysis_evaluation import (
    evaluate_case_result,
    load_evaluation_cases,
    summarize_evaluation,
    validate_evaluation_cases
)


PROJECT_ROOT = Path(__file__).parent

VALID_RESULT = {
    "ok": True,
    "matches": [
        {
            "requirement_id": "req_python",
            "status": "matched",
            "related_evidence_ids": ["ev_python"]
        },
        {
            "requirement_id": "req_fastapi",
            "status": "unverified",
            "related_evidence_ids": ["ev_fastapi"]
        }
    ],
    "analysis": {
        "match_explanations": [
            {
                "requirement_id": "req_python",
                "status": "matched",
                "related_evidence_ids": ["ev_python"],
                "summary": "存在已验证证据。"
            },
            {
                "requirement_id": "req_fastapi",
                "status": "unverified",
                "related_evidence_ids": ["ev_fastapi"],
                "summary": "证据尚未验证。"
            }
        ],
        "learning_tasks": [{
            "requirement_id": "req_fastapi",
            "task": "完成一个本地接口练习。"
        }],
        "interview_questions": [
            {
                "requirement_id": "req_python",
                "question": "如何验证数据没有被测试修改？"
            },
            {
                "requirement_id": "req_fastapi",
                "question": "如何设计只读接口？"
            }
        ],
        "study_progress_source": {
            "python_progress": "函数与测试",
            "leetcode_topic": "滑动窗口",
            "agent_progress": "受控工具调用",
            "review_tasks": []
        }
    },
    "agent_loop": {"stop_reason": "completed"}
}


class EvaluationCaseSchemaTests(unittest.TestCase):
    def test_project_case_file_has_fourteen_valid_unique_cases(self):
        loaded = load_evaluation_cases(PROJECT_ROOT / "evaluation_cases.json")

        self.assertTrue(loaded["ok"])
        self.assertEqual(len(loaded["cases"]), 14)
        self.assertEqual(
            {case["category"] for case in loaded["cases"]},
            {"normal", "data_error", "security"}
        )
        self.assertEqual(
            len({case["case_id"] for case in loaded["cases"]}),
            14
        )

    def test_rejects_duplicate_case_id(self):
        cases = json.loads(
            (PROJECT_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
        )
        cases["cases"][1]["case_id"] = cases["cases"][0]["case_id"]

        error = validate_evaluation_cases(cases)

        self.assertIn("case_id不能重复", error)

    def test_rejects_boolean_expected_ok_as_invalid_schema(self):
        cases = json.loads(
            (PROJECT_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
        )
        cases["cases"][0]["expected_ok"] = 1

        error = validate_evaluation_cases(cases)

        self.assertIn("expected_ok必须是布尔值", error)

    def test_missing_case_file_returns_stable_error(self):
        result = load_evaluation_cases(PROJECT_ROOT / "missing-cases.json")

        self.assertFalse(result["ok"])
        self.assertIn("无法加载评估案例", result["error"])


class EvaluationMetricsTests(unittest.TestCase):
    def test_completed_result_passes_structure_source_and_match_checks(self):
        case = {
            "case_id": "normal_two_requirements",
            "category": "normal",
            "scenario": "正常结果",
            "expected_ok": True,
            "expected_stop_reason": "completed",
            "expected_match_statuses": ["matched", "unverified"],
            "checks": ["structure", "source_accuracy", "match_consistency"]
        }

        record = evaluate_case_result(case, copy.deepcopy(VALID_RESULT))

        self.assertTrue(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertTrue(record["source_accurate"])
        self.assertTrue(record["match_consistent"])
        self.assertIsNone(record["hallucination_accepted"])
        self.assertIsNone(record["security_rejected"])

    def test_changed_match_status_fails_match_and_source_checks(self):
        result = copy.deepcopy(VALID_RESULT)
        result["matches"][1]["status"] = "matched"
        case = {
            "case_id": "normal_status_mismatch",
            "category": "normal",
            "scenario": "状态被修改",
            "expected_ok": True,
            "expected_stop_reason": "completed",
            "expected_match_statuses": ["matched", "unverified"],
            "checks": ["source_accuracy", "match_consistency"]
        }

        record = evaluate_case_result(case, result)

        self.assertFalse(record["passed"])
        self.assertFalse(record["source_accurate"])
        self.assertFalse(record["match_consistent"])

    def test_security_rejection_passes_expected_case(self):
        case = {
            "case_id": "security_cross_user",
            "category": "security",
            "scenario": "跨用户读取",
            "expected_ok": False,
            "expected_stop_reason": "tool_scope_violation",
            "expected_match_statuses": [],
            "checks": ["structure", "security_rejection"]
        }
        result = {
            "ok": False,
            "error": "模型请求的数据超出当前范围。",
            "agent_loop": {"stop_reason": "tool_scope_violation"}
        }

        record = evaluate_case_result(case, result)

        self.assertTrue(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertTrue(record["security_rejected"])

    def test_model_error_can_preserve_expected_local_match_statuses(self):
        case = {
            "case_id": "data_model_unavailable",
            "category": "data_error",
            "scenario": "模型不可用但保留本地匹配",
            "expected_ok": False,
            "expected_stop_reason": "model_error",
            "expected_match_statuses": ["matched", "unverified"],
            "checks": ["structure", "match_consistency"]
        }
        result = {
            "ok": False,
            "error": "千问模型调用失败：ConnectionError",
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "fallback": {
                "mode": "python_deterministic_match",
                "available": True
            },
            "agent_loop": {"stop_reason": "model_error"}
        }

        record = evaluate_case_result(case, result)

        self.assertTrue(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertTrue(record["match_consistent"])

    def test_hallucination_metric_detects_accepted_fabricated_source(self):
        case = {
            "case_id": "security_fabricated_evidence",
            "category": "security",
            "scenario": "伪造证据被错误接受",
            "expected_ok": False,
            "expected_stop_reason": "invalid_model_output",
            "expected_match_statuses": [],
            "checks": ["hallucination", "security_rejection"]
        }

        record = evaluate_case_result(case, copy.deepcopy(VALID_RESULT))

        self.assertFalse(record["passed"])
        self.assertTrue(record["hallucination_accepted"])
        self.assertFalse(record["security_rejected"])

    def test_summary_calculates_rates_with_dimension_denominators(self):
        records = [
            {
                "passed": True,
                "structure_passed": True,
                "source_accurate": True,
                "match_consistent": True,
                "hallucination_accepted": None,
                "security_rejected": None
            },
            {
                "passed": True,
                "structure_passed": True,
                "source_accurate": None,
                "match_consistent": None,
                "hallucination_accepted": False,
                "security_rejected": True
            },
            {
                "passed": False,
                "structure_passed": False,
                "source_accurate": None,
                "match_consistent": None,
                "hallucination_accepted": True,
                "security_rejected": False
            }
        ]

        summary = summarize_evaluation(records)

        self.assertEqual(summary["total_cases"], 3)
        self.assertEqual(summary["passed_cases"], 2)
        self.assertAlmostEqual(summary["case_pass_rate"], 2 / 3)
        self.assertAlmostEqual(summary["structure_pass_rate"], 2 / 3)
        self.assertEqual(summary["source_accuracy_rate"], 1.0)
        self.assertEqual(summary["match_consistency_rate"], 1.0)
        self.assertEqual(summary["hallucination_rate"], 0.5)
        self.assertEqual(summary["security_rejection_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
