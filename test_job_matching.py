import copy
import json
import tempfile
import unittest
from pathlib import Path

from job_matching import (
    get_candidate_evidence,
    get_job_requirements,
    match_job_requirements
)


BASE_JOB = {
    "job_id": "demo_job",
    "title": "脱敏岗位",
    "requirements": [
        {
            "requirement_id": "req_python",
            "skill_id": "python",
            "description": "能够使用Python完成项目开发",
            "category": "required",
            "priority": 1
        }
    ]
}


def make_evidence(evidence_id, level, verified, skill_id="python"):
    return {
        "evidence_id": evidence_id,
        "skill_id": skill_id,
        "description": f"{skill_id}脱敏证据",
        "level": level,
        "source": "V0.9b测试数据",
        "verified": verified
    }


def make_candidate(*evidence_items):
    return {
        "username": "test_user",
        "evidence": list(evidence_items)
    }


def expected_result(status, evidence_ids):
    requirement = BASE_JOB["requirements"][0]
    return {
        **requirement,
        "status": status,
        "related_evidence_ids": evidence_ids
    }


class MatchJobRequirementsMatrixTests(unittest.TestCase):
    """验证 matched、partial、missing、unverified 的确定性矩阵。"""

    def assert_single_result(self, candidate, status, evidence_ids):
        result = match_job_requirements(copy.deepcopy(BASE_JOB), candidate)

        self.assertEqual(result, [expected_result(status, evidence_ids)])

    def test_missing_when_no_related_evidence_exists(self):
        candidate = make_candidate(
            make_evidence("ev_sql", "production", True, skill_id="sql")
        )

        self.assert_single_result(candidate, "missing", [])

    def test_unverified_when_all_related_evidence_is_unverified(self):
        candidate = make_candidate(
            make_evidence("ev_python_plan", "project", False)
        )

        self.assert_single_result(
            candidate,
            "unverified",
            ["ev_python_plan"]
        )

    def test_partial_for_verified_learning_evidence(self):
        candidate = make_candidate(
            make_evidence("ev_python_learning", "learning", True)
        )

        self.assert_single_result(
            candidate,
            "partial",
            ["ev_python_learning"]
        )

    def test_partial_for_verified_practice_evidence(self):
        candidate = make_candidate(
            make_evidence("ev_python_practice", "practice", True)
        )

        self.assert_single_result(
            candidate,
            "partial",
            ["ev_python_practice"]
        )

    def test_matched_for_verified_project_evidence(self):
        candidate = make_candidate(
            make_evidence("ev_python_project", "project", True)
        )

        self.assert_single_result(
            candidate,
            "matched",
            ["ev_python_project"]
        )

    def test_matched_for_verified_production_evidence(self):
        candidate = make_candidate(
            make_evidence("ev_python_production", "production", True)
        )

        self.assert_single_result(
            candidate,
            "matched",
            ["ev_python_production"]
        )

    def test_unverified_project_does_not_override_verified_practice(self):
        candidate = make_candidate(
            make_evidence("ev_python_unverified_project", "project", False),
            make_evidence("ev_python_practice", "practice", True)
        )

        self.assert_single_result(
            candidate,
            "partial",
            ["ev_python_unverified_project", "ev_python_practice"]
        )

    def test_strongest_verified_level_determines_status(self):
        candidate = make_candidate(
            make_evidence("ev_python_learning", "learning", True),
            make_evidence("ev_python_project", "project", True)
        )

        self.assert_single_result(
            candidate,
            "matched",
            ["ev_python_learning", "ev_python_project"]
        )

    def test_project_data_produces_expected_statuses_in_requirement_order(self):
        job = json.loads(Path("jobs.json").read_text(encoding="utf-8"))["jobs"][0]
        candidate = json.loads(
            Path("candidate_evidence.json").read_text(encoding="utf-8")
        )["candidates"][0]

        result = match_job_requirements(job, candidate)

        self.assertEqual(
            [item["status"] for item in result],
            ["matched", "matched", "unverified"]
        )
        self.assertEqual(
            [item["requirement_id"] for item in result],
            ["req_python", "req_agent_tool_calling", "req_fastapi"]
        )

    def test_saved_example_matches_project_result(self):
        job_result = get_job_requirements(
            "demo_ai_agent_intern",
            Path("jobs.json")
        )
        evidence_result = get_candidate_evidence(
            "test_user",
            Path("candidate_evidence.json")
        )
        job = {
            "job_id": job_result["job_id"],
            "title": job_result["title"],
            "requirements": job_result["requirements"]
        }
        candidate = {
            "username": evidence_result["username"],
            "evidence": evidence_result["evidence"]
        }
        actual = {
            "job_id": job_result["job_id"],
            "username": evidence_result["username"],
            "matches": match_job_requirements(job, candidate)
        }
        saved_example = json.loads(
            Path("examples/careeragent_v0_9b_job_match_output.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(actual, saved_example)

    def test_rejects_invalid_job_before_matching(self):
        job = copy.deepcopy(BASE_JOB)
        job["requirements"][0]["category"] = "optional"

        with self.assertRaisesRegex(
            ValueError,
            "第1项岗位要求字段category必须是required或preferred"
        ):
            match_job_requirements(job, make_candidate())

    def test_rejects_invalid_candidate_before_matching(self):
        candidate = make_candidate(
            make_evidence("ev_python", "expert", True)
        )

        with self.assertRaisesRegex(
            ValueError,
            "第1项个人证据字段level必须是learning、practice、project或production"
        ):
            match_job_requirements(copy.deepcopy(BASE_JOB), candidate)


class GetJobRequirementsTests(unittest.TestCase):
    """验证岗位要求工具只返回一个已校验岗位且不修改文件。"""

    def test_returns_project_job_without_changing_file(self):
        jobs_path = Path("jobs.json")
        content_before = jobs_path.read_bytes()

        result = get_job_requirements("demo_ai_agent_intern", jobs_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "demo_ai_agent_intern")
        self.assertEqual(result["title"], "AI Agent开发实习生（脱敏示例）")
        self.assertEqual(len(result["requirements"]), 3)
        self.assertEqual(
            set(result),
            {"ok", "job_id", "title", "requirements"}
        )
        self.assertEqual(jobs_path.read_bytes(), content_before)

    def test_rejects_blank_job_id_before_reading_file(self):
        result = get_job_requirements("   ", Path("missing-jobs.json"))

        self.assertEqual(result, {"ok": False, "error": "岗位ID不能为空。"})

    def test_returns_error_for_unknown_job(self):
        result = get_job_requirements("unknown_job", Path("jobs.json"))

        self.assertEqual(
            result,
            {"ok": False, "error": "未找到岗位：unknown_job"}
        )

    def test_returns_error_when_job_file_is_missing(self):
        result = get_job_requirements(
            "demo_ai_agent_intern",
            Path("missing-jobs.json")
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "无法加载岗位数据，请检查文件路径和JSON格式。"
            }
        )

    def test_returns_error_when_job_json_is_broken(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs_path = Path(temp_dir) / "jobs.json"
            jobs_path.write_text("{", encoding="utf-8")

            result = get_job_requirements("demo_job", jobs_path)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "无法加载岗位数据，请检查文件路径和JSON格式。"
            }
        )

    def test_rejects_invalid_job_root_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs_path = Path(temp_dir) / "jobs.json"
            jobs_path.write_text(
                json.dumps({"jobs": []}, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_job_requirements("demo_job", jobs_path)

        self.assertEqual(
            result,
            {"ok": False, "error": "岗位数据字段jobs必须是非空列表。"}
        )


class GetCandidateEvidenceTests(unittest.TestCase):
    """验证候选人证据工具只返回一个已校验用户且不修改文件。"""

    def test_returns_project_candidate_without_changing_file(self):
        evidence_path = Path("candidate_evidence.json")
        content_before = evidence_path.read_bytes()

        result = get_candidate_evidence("test_user", evidence_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["username"], "test_user")
        self.assertEqual(len(result["evidence"]), 3)
        self.assertEqual(set(result), {"ok", "username", "evidence"})
        self.assertEqual(evidence_path.read_bytes(), content_before)

    def test_rejects_blank_username_before_reading_file(self):
        result = get_candidate_evidence(" ", Path("missing-evidence.json"))

        self.assertEqual(result, {"ok": False, "error": "用户名不能为空。"})

    def test_returns_error_for_unknown_username(self):
        result = get_candidate_evidence("unknown_user", Path("candidate_evidence.json"))

        self.assertEqual(
            result,
            {"ok": False, "error": "未找到用户：unknown_user"}
        )

    def test_returns_error_when_evidence_file_is_missing(self):
        result = get_candidate_evidence(
            "test_user",
            Path("missing-evidence.json")
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "无法加载个人证据数据，请检查文件路径和JSON格式。"
            }
        )

    def test_returns_error_when_evidence_json_is_broken(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = Path(temp_dir) / "candidate_evidence.json"
            evidence_path.write_text("{", encoding="utf-8")

            result = get_candidate_evidence("test_user", evidence_path)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "无法加载个人证据数据，请检查文件路径和JSON格式。"
            }
        )

    def test_rejects_invalid_candidate_root_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = Path(temp_dir) / "candidate_evidence.json"
            evidence_path.write_text(
                json.dumps({"candidates": []}, ensure_ascii=False),
                encoding="utf-8"
            )

            result = get_candidate_evidence("test_user", evidence_path)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": "个人证据字段candidates必须是非空列表。"
            }
        )


if __name__ == "__main__":
    unittest.main()
