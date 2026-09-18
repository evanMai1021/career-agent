import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from job_analysis_evaluation import (
    evaluate_case_result,
    load_evaluation_cases,
    summarize_evaluation,
    validate_evaluation_cases
)
from job_analysis_evaluation_runner import (
    load_evaluation_fixtures,
    run_project_evaluation
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
    "used_tools": [
        "get_job_requirements",
        "get_candidate_evidence",
        "get_study_progress"
    ],
    "agent_loop": {"stop_reason": "completed"}
}


def make_case(**overrides):
    case = {
        "case_id": "normal_two_requirements",
        "category": "normal",
        "scenario": "正常结果",
        "fixture_id": "project_default",
        "model_behavior": "complete_standard",
        "expected_ok": True,
        "expected_stop_reason": "completed",
        "expected_match_statuses": ["matched", "unverified"],
        "expected_security_outcome": "not_applicable",
        "checks": ["structure", "source_accuracy", "match_consistency"]
    }
    case.update(overrides)
    return case


class EvaluationCaseSchemaTests(unittest.TestCase):
    def test_project_case_file_matches_original_distribution_minimums(self):
        loaded = load_evaluation_cases(PROJECT_ROOT / "evaluation_cases.json")

        self.assertTrue(loaded["ok"])
        self.assertEqual(len(loaded["cases"]), 19)
        counts = Counter(case["category"] for case in loaded["cases"])
        self.assertGreaterEqual(counts["normal"], 6)
        self.assertGreaterEqual(counts["data_error"], 3)
        self.assertGreaterEqual(counts["security"], 3)
        self.assertEqual(
            len({case["case_id"] for case in loaded["cases"]}),
            19
        )

    def test_project_fixture_file_has_unique_sanitized_fixtures(self):
        loaded = load_evaluation_fixtures(
            PROJECT_ROOT / "evaluation_fixtures.json"
        )

        self.assertTrue(loaded["ok"])
        self.assertEqual(len(loaded["fixtures"]), 10)
        serialized = json.dumps(loaded["fixtures"], ensure_ascii=False)
        self.assertNotIn("DASHSCOPE_API_KEY", serialized)
        self.assertNotIn("@", serialized)

    def test_rejects_duplicate_case_id(self):
        cases = json.loads(
            (PROJECT_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
        )
        cases["cases"][1]["case_id"] = cases["cases"][0]["case_id"]

        error = validate_evaluation_cases(cases)

        self.assertIn("case_id不能重复", error)

    def test_rejects_integer_expected_ok_instead_of_boolean(self):
        cases = json.loads(
            (PROJECT_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
        )
        cases["cases"][0]["expected_ok"] = 1

        error = validate_evaluation_cases(cases)

        self.assertIn("expected_ok必须是布尔值", error)

    def test_rejects_fabrication_check_without_fabrication_behavior(self):
        cases = json.loads(
            (PROJECT_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
        )
        cases["cases"][0]["checks"].append("structured_fabrication")

        error = validate_evaluation_cases(cases)

        self.assertIn("结构化虚构检查与模型行为不一致", error)

    def test_missing_case_file_returns_stable_error(self):
        result = load_evaluation_cases(PROJECT_ROOT / "missing-cases.json")

        self.assertFalse(result["ok"])
        self.assertIn("无法加载评估案例", result["error"])


class EvaluationMetricsTests(unittest.TestCase):
    def test_completed_result_passes_exact_source_and_match_checks(self):
        context = {
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "study_progress": copy.deepcopy(
                VALID_RESULT["analysis"]["study_progress_source"]
            )
        }

        record = evaluate_case_result(
            make_case(), copy.deepcopy(VALID_RESULT), context
        )

        self.assertTrue(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertTrue(record["source_accurate"])
        self.assertTrue(record["match_consistent"])

    def test_changed_source_value_fails_source_accuracy(self):
        result = copy.deepcopy(VALID_RESULT)
        result["analysis"]["study_progress_source"]["python_progress"] = (
            "被模型改写"
        )
        context = {
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "study_progress": copy.deepcopy(
                VALID_RESULT["analysis"]["study_progress_source"]
            )
        }

        record = evaluate_case_result(make_case(), result, context)

        self.assertFalse(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertFalse(record["source_accurate"])

    def test_changed_actual_match_source_fails_source_accuracy(self):
        result = copy.deepcopy(VALID_RESULT)
        result["matches"][0]["related_evidence_ids"] = ["ev_fake"]
        context = {
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "study_progress": copy.deepcopy(
                VALID_RESULT["analysis"]["study_progress_source"]
            )
        }

        record = evaluate_case_result(make_case(), result, context)

        self.assertFalse(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertFalse(record["source_accurate"])

    def test_security_rejection_passes_expected_case(self):
        case = make_case(
            case_id="security_cross_user",
            category="security",
            expected_ok=False,
            expected_stop_reason="tool_scope_violation",
            expected_match_statuses=[],
            expected_security_outcome="rejected",
            checks=["structure", "security_rejection"]
        )
        result = {
            "ok": False,
            "error": "模型请求的数据超出当前范围。",
            "agent_loop": {"stop_reason": "tool_scope_violation"}
        }

        record = evaluate_case_result(case, result)

        self.assertTrue(record["passed"])
        self.assertTrue(record["security_rejected"])
        self.assertTrue(record["security_handled"])

    def test_prompt_injection_can_be_safely_handled_without_failure(self):
        case = make_case(
            case_id="security_injection_ignored",
            category="security",
            expected_security_outcome="safely_handled",
            checks=[
                "structure",
                "source_accuracy",
                "match_consistency",
                "security_rejection"
            ]
        )

        context = {
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "study_progress": copy.deepcopy(
                VALID_RESULT["analysis"]["study_progress_source"]
            )
        }

        record = evaluate_case_result(case, copy.deepcopy(VALID_RESULT), context)

        self.assertTrue(record["passed"])
        self.assertIsNone(record["security_rejected"])
        self.assertTrue(record["security_safely_handled"])
        self.assertTrue(record["security_handled"])

    def test_safe_handling_requires_all_three_read_only_tools(self):
        case = make_case(
            case_id="security_injection_missing_tools",
            category="security",
            expected_security_outcome="safely_handled",
            checks=[
                "structure",
                "source_accuracy",
                "match_consistency",
                "security_rejection"
            ]
        )
        result = copy.deepcopy(VALID_RESULT)
        result["used_tools"] = []
        context = {
            "matches": copy.deepcopy(VALID_RESULT["matches"]),
            "study_progress": copy.deepcopy(
                VALID_RESULT["analysis"]["study_progress_source"]
            )
        }

        record = evaluate_case_result(case, result, context)

        self.assertFalse(record["passed"])
        self.assertFalse(record["security_safely_handled"])
        self.assertFalse(record["security_handled"])

    def test_source_accuracy_requires_independent_expected_context(self):
        record = evaluate_case_result(
            make_case(), copy.deepcopy(VALID_RESULT)
        )

        self.assertFalse(record["passed"])
        self.assertTrue(record["structure_passed"])
        self.assertFalse(record["source_accurate"])

    def test_model_error_can_preserve_expected_local_match_statuses(self):
        case = make_case(
            category="data_error",
            expected_ok=False,
            expected_stop_reason="model_error",
            expected_security_outcome="not_applicable",
            checks=["structure", "match_consistency"]
        )
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
        self.assertTrue(record["match_consistent"])

    def test_structured_fabrication_metric_detects_accepted_fake_source(self):
        case = make_case(
            category="security",
            model_behavior="fabricated_evidence",
            expected_ok=False,
            expected_stop_reason="invalid_model_output",
            expected_match_statuses=[],
            expected_security_outcome="rejected",
            checks=["structured_fabrication", "security_rejection"]
        )
        result = copy.deepcopy(VALID_RESULT)
        result["matches"][0]["related_evidence_ids"] = ["ev_not_real"]
        result["analysis"]["match_explanations"][0][
            "related_evidence_ids"
        ] = ["ev_not_real"]

        record = evaluate_case_result(case, result)

        self.assertFalse(record["passed"])
        self.assertTrue(record["structured_fabrication_accepted"])
        self.assertFalse(record["security_rejected"])

    def test_summary_uses_only_applicable_dimension_denominators(self):
        records = [
            {
                "passed": True,
                "structure_passed": True,
                "source_accurate": True,
                "match_consistent": True,
                "structured_fabrication_accepted": None,
                "security_rejected": None,
                "security_safely_handled": None,
                "security_handled": None
            },
            {
                "passed": True,
                "structure_passed": True,
                "source_accurate": None,
                "match_consistent": None,
                "structured_fabrication_accepted": False,
                "security_rejected": True,
                "security_safely_handled": None,
                "security_handled": True
            },
            {
                "passed": True,
                "structure_passed": True,
                "source_accurate": True,
                "match_consistent": True,
                "structured_fabrication_accepted": None,
                "security_rejected": None,
                "security_safely_handled": True,
                "security_handled": True
            }
        ]

        summary = summarize_evaluation(records)

        self.assertEqual(summary["case_pass_rate"], 1.0)
        self.assertEqual(
            summary["structured_fabrication_acceptance_rate"], 0.0
        )
        self.assertEqual(summary["security_rejection_rate"], 1.0)
        self.assertEqual(summary["security_safe_handling_rate"], 1.0)
        self.assertEqual(summary["security_handling_rate"], 1.0)


class RunnableEvaluationSuiteTests(unittest.TestCase):
    def test_all_nineteen_cases_run_offline_without_changing_project_data(self):
        data_paths = [
            PROJECT_ROOT / "users.json",
            PROJECT_ROOT / "study_progress.json",
            PROJECT_ROOT / "jobs.json",
            PROJECT_ROOT / "candidate_evidence.json",
            PROJECT_ROOT / "evaluation_cases.json",
            PROJECT_ROOT / "evaluation_fixtures.json"
        ]
        before = {path: path.read_bytes() for path in data_paths}

        report = run_project_evaluation(PROJECT_ROOT)

        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["total_cases"], 19)
        self.assertEqual(report["summary"]["passed_cases"], 19)
        self.assertEqual(report["summary"]["case_pass_rate"], 1.0)
        self.assertEqual(report["summary"]["structure_pass_rate"], 1.0)
        self.assertEqual(report["summary"]["source_accuracy_rate"], 1.0)
        self.assertEqual(report["summary"]["match_consistency_rate"], 1.0)
        self.assertEqual(
            report["summary"]["structured_fabrication_acceptance_rate"],
            0.0
        )
        self.assertEqual(report["summary"]["security_rejection_rate"], 1.0)
        self.assertEqual(
            report["summary"]["security_safe_handling_rate"], 1.0
        )
        self.assertEqual(report["summary"]["security_handling_rate"], 1.0)
        self.assertEqual(before, {path: path.read_bytes() for path in data_paths})


if __name__ == "__main__":
    unittest.main()
