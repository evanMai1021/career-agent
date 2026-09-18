import copy
import json
import unittest
from pathlib import Path

from job_data import (
    validate_candidate_evidence,
    validate_candidate_evidence_data,
    validate_job,
    validate_jobs_data
)


VALID_JOB = {
    "job_id": "demo_ai_agent_intern",
    "title": "AI Agent开发实习生（脱敏示例）",
    "requirements": [
        {
            "requirement_id": "req_python",
            "skill_id": "python",
            "description": "能够使用Python完成数据处理和自动化测试",
            "category": "required",
            "priority": 1
        }
    ]
}

VALID_CANDIDATE = {
    "username": "test_user",
    "evidence": [
        {
            "evidence_id": "ev_python_tests",
            "skill_id": "python",
            "description": "CareerAgent V0.8.1共有49项离线测试通过",
            "level": "project",
            "source": "CareerAgent V0.8.1测试结果",
            "verified": True
        }
    ]
}


class JobValidationTests(unittest.TestCase):
    """验证单个岗位和岗位数据根结构。"""

    def test_accepts_valid_job(self):
        self.assertIsNone(validate_job(copy.deepcopy(VALID_JOB)))

    def test_rejects_blank_job_title(self):
        job = copy.deepcopy(VALID_JOB)
        job["title"] = "   "

        self.assertEqual(
            validate_job(job),
            "岗位字段title必须是非空字符串。"
        )

    def test_rejects_unknown_requirement_category(self):
        job = copy.deepcopy(VALID_JOB)
        job["requirements"][0]["category"] = "optional"

        self.assertEqual(
            validate_job(job),
            "第1项岗位要求字段category必须是required或preferred。"
        )

    def test_rejects_non_string_requirement_category(self):
        job = copy.deepcopy(VALID_JOB)
        job["requirements"][0]["category"] = []

        self.assertEqual(
            validate_job(job),
            "第1项岗位要求字段category必须是required或preferred。"
        )

    def test_rejects_duplicate_requirement_id(self):
        job = copy.deepcopy(VALID_JOB)
        job["requirements"].append(copy.deepcopy(job["requirements"][0]))

        self.assertEqual(
            validate_job(job),
            "岗位要求ID不能重复：req_python"
        )

    def test_rejects_boolean_priority(self):
        """bool 是 int 的子类，但不能被当成岗位优先级 1。"""
        job = copy.deepcopy(VALID_JOB)
        job["requirements"][0]["priority"] = True

        self.assertEqual(
            validate_job(job),
            "第1项岗位要求字段priority必须是1、2或3。"
        )

    def test_rejects_duplicate_job_id_in_root_data(self):
        data = {"jobs": [copy.deepcopy(VALID_JOB), copy.deepcopy(VALID_JOB)]}

        self.assertEqual(
            validate_jobs_data(data),
            "岗位ID不能重复：demo_ai_agent_intern"
        )

    def test_project_jobs_json_matches_schema(self):
        data = json.loads(
            Path("jobs.json").read_text(encoding="utf-8")
        )

        self.assertIsNone(validate_jobs_data(data))


class CandidateEvidenceValidationTests(unittest.TestCase):
    """验证个人证据结构，并明确记录能力证据是否已经核实。"""

    def test_accepts_valid_candidate_evidence(self):
        self.assertIsNone(
            validate_candidate_evidence(copy.deepcopy(VALID_CANDIDATE))
        )

    def test_allows_empty_evidence_list(self):
        candidate = {"username": "test_user", "evidence": []}

        self.assertIsNone(validate_candidate_evidence(candidate))

    def test_rejects_blank_evidence_source(self):
        candidate = copy.deepcopy(VALID_CANDIDATE)
        candidate["evidence"][0]["source"] = " "

        self.assertEqual(
            validate_candidate_evidence(candidate),
            "第1项个人证据字段source必须是非空字符串。"
        )

    def test_rejects_non_boolean_verified_value(self):
        candidate = copy.deepcopy(VALID_CANDIDATE)
        candidate["evidence"][0]["verified"] = "yes"

        self.assertEqual(
            validate_candidate_evidence(candidate),
            "第1项个人证据字段verified必须是布尔值。"
        )

    def test_rejects_unknown_evidence_level(self):
        candidate = copy.deepcopy(VALID_CANDIDATE)
        candidate["evidence"][0]["level"] = "expert"

        self.assertEqual(
            validate_candidate_evidence(candidate),
            "第1项个人证据字段level必须是learning、practice、project或production。"
        )

    def test_rejects_non_string_evidence_level(self):
        candidate = copy.deepcopy(VALID_CANDIDATE)
        candidate["evidence"][0]["level"] = []

        self.assertEqual(
            validate_candidate_evidence(candidate),
            "第1项个人证据字段level必须是learning、practice、project或production。"
        )

    def test_rejects_duplicate_evidence_id(self):
        candidate = copy.deepcopy(VALID_CANDIDATE)
        candidate["evidence"].append(copy.deepcopy(candidate["evidence"][0]))

        self.assertEqual(
            validate_candidate_evidence(candidate),
            "个人证据ID不能重复：ev_python_tests"
        )

    def test_project_candidate_evidence_json_matches_schema(self):
        data = json.loads(
            Path("candidate_evidence.json").read_text(encoding="utf-8")
        )

        self.assertIsNone(validate_candidate_evidence_data(data))

    def test_rejects_duplicate_username_in_root_data(self):
        data = {
            "candidates": [
                copy.deepcopy(VALID_CANDIDATE),
                copy.deepcopy(VALID_CANDIDATE)
            ]
        }

        self.assertEqual(
            validate_candidate_evidence_data(data),
            "候选人用户名不能重复：test_user"
        )


if __name__ == "__main__":
    unittest.main()
