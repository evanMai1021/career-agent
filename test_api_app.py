"""CareerAgent V1.3 本地只读 HTTP API 的离线契约测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import (
    DEFAULT_EVIDENCE_FILE,
    DEFAULT_JOBS_FILE,
    app,
    create_app,
)


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_only_service_status(self):
        response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class JobRequirementsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.jobs_path = Path(self.temp_dir.name) / "jobs.json"
        self.job = {
            "job_id": "demo_python",
            "title": "脱敏 Python 岗位",
            "requirements": [
                {
                    "requirement_id": "req_python",
                    "skill_id": "python",
                    "description": "使用 Python 完成功能开发",
                    "category": "required",
                    "priority": 1,
                }
            ],
        }
        self.jobs_path.write_text(
            json.dumps({"jobs": [self.job]}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.client = TestClient(create_app(jobs_file=self.jobs_path))

    def test_returns_validated_job_without_changing_file(self):
        before = self.jobs_path.read_bytes()

        response = self.client.get("/jobs/demo_python/requirements")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.job)
        self.assertEqual(self.jobs_path.read_bytes(), before)

    def test_unknown_job_returns_404_without_echoing_query(self):
        response = self.client.get("/jobs/not_found/requirements")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "岗位不存在。"})

    def test_missing_or_invalid_data_returns_503_without_file_path(self):
        self.jobs_path.write_text("{broken", encoding="utf-8")

        response = self.client.get("/jobs/demo_python/requirements")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "岗位数据暂不可用。"})
        self.assertNotIn(str(self.jobs_path), response.text)

    def test_rejects_client_supplied_file_path(self):
        response = self.client.get(
            "/jobs/demo_python/requirements",
            params={"jobs_file": ".env"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "不接受查询参数。"})


class AnalysisEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        temp_path = Path(self.temp_dir.name)
        self.jobs_path = temp_path / "jobs.json"
        self.evidence_path = temp_path / "candidate_evidence.json"
        self.jobs_data = {
            "jobs": [
                {
                    "job_id": "demo_python",
                    "title": "脱敏 Python 岗位",
                    "requirements": [
                        {
                            "requirement_id": "req_python",
                            "skill_id": "python",
                            "description": "使用 Python 完成功能开发",
                            "category": "required",
                            "priority": 1,
                        },
                        {
                            "requirement_id": "req_fastapi",
                            "skill_id": "fastapi",
                            "description": "了解 Python Web API 开发",
                            "category": "preferred",
                            "priority": 2,
                        },
                    ],
                }
            ]
        }
        self.evidence_data = {
            "candidates": [
                {
                    "username": "demo_user",
                    "evidence": [
                        {
                            "evidence_id": "ev_python",
                            "skill_id": "python",
                            "description": "完成脱敏 Python 项目",
                            "level": "project",
                            "source": "脱敏测试夹具",
                            "verified": True,
                        },
                        {
                            "evidence_id": "ev_fastapi",
                            "skill_id": "fastapi",
                            "description": "尚未验证的 FastAPI 描述",
                            "level": "learning",
                            "source": "脱敏测试夹具",
                            "verified": False,
                        },
                    ],
                }
            ]
        }
        self.jobs_path.write_text(
            json.dumps(self.jobs_data, ensure_ascii=False),
            encoding="utf-8",
        )
        self.evidence_path.write_text(
            json.dumps(self.evidence_data, ensure_ascii=False),
            encoding="utf-8",
        )
        self.client = TestClient(
            create_app(
                jobs_file=self.jobs_path,
                evidence_file=self.evidence_path,
            )
        )

    def test_returns_deterministic_matches_and_trusted_facts_without_writes(self):
        jobs_before = self.jobs_path.read_bytes()
        evidence_before = self.evidence_path.read_bytes()

        response = self.client.post(
            "/analyses",
            json={"username": "demo_user", "job_id": "demo_python"},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["username"], "demo_user")
        self.assertEqual(result["job_id"], "demo_python")
        self.assertEqual(result["analysis_mode"], "offline_deterministic")
        self.assertIs(result["model_generated"], False)
        self.assertEqual(
            [match["status"] for match in result["matches"]],
            ["matched", "unverified"],
        )
        self.assertEqual(
            result["trusted_facts"],
            [
                {
                    "requirement_id": "req_python",
                    "skill_id": "python",
                    "status": "matched",
                    "related_evidence_ids": ["ev_python"],
                    "verified_evidence_ids": ["ev_python"],
                    "unverified_evidence_ids": [],
                    "origin": "python_deterministic_match",
                },
                {
                    "requirement_id": "req_fastapi",
                    "skill_id": "fastapi",
                    "status": "unverified",
                    "related_evidence_ids": ["ev_fastapi"],
                    "verified_evidence_ids": [],
                    "unverified_evidence_ids": ["ev_fastapi"],
                    "origin": "python_deterministic_match",
                },
            ],
        )
        self.assertNotIn("尚未验证的 FastAPI 描述", response.text)
        self.assertEqual(self.jobs_path.read_bytes(), jobs_before)
        self.assertEqual(self.evidence_path.read_bytes(), evidence_before)

    def test_unknown_job_or_candidate_returns_scoped_404(self):
        cases = [
            (
                {"username": "demo_user", "job_id": "other_job"},
                "岗位不存在。",
            ),
            (
                {"username": "other_user", "job_id": "demo_python"},
                "候选人不存在。",
            ),
        ]
        for payload, expected_detail in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/analyses", json=payload)

                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.json(),
                    {"detail": expected_detail},
                )

    def test_rejects_client_controlled_paths_models_and_outputs(self):
        forbidden_fields = {
            "jobs_file": ".env",
            "evidence_file": "candidate_evidence.json",
            "model": "external-model",
            "output_file": "result.json",
        }
        for field, value in forbidden_fields.items():
            with self.subTest(field=field):
                response = self.client.post(
                    "/analyses",
                    json={
                        "username": "demo_user",
                        "job_id": "demo_python",
                        field: value,
                    },
                )

                self.assertEqual(response.status_code, 422)

    def test_rejects_query_parameters(self):
        response = self.client.post(
            "/analyses",
            params={"model": "external-model"},
            json={"username": "demo_user", "job_id": "demo_python"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "不接受查询参数。"})

    def test_invalid_evidence_data_returns_503_without_file_path(self):
        self.evidence_path.write_text("{broken", encoding="utf-8")

        response = self.client.post(
            "/analyses",
            json={"username": "demo_user", "job_id": "demo_python"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "候选人证据数据暂不可用。"},
        )
        self.assertNotIn(str(self.evidence_path), response.text)


class ProjectAnalysisEndpointTests(unittest.TestCase):
    def test_default_app_reproduces_project_analysis_without_writes(self):
        jobs_before = DEFAULT_JOBS_FILE.read_bytes()
        evidence_before = DEFAULT_EVIDENCE_FILE.read_bytes()
        saved_example_path = (
            Path(__file__).resolve().parent
            / "examples"
            / "careeragent_v1_3_api_analysis_output.json"
        )
        saved_example = json.loads(saved_example_path.read_text(encoding="utf-8"))

        response = TestClient(app).post(
            "/analyses",
            json={
                "username": "test_user",
                "job_id": "demo_ai_agent_intern",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result, saved_example)
        self.assertEqual(
            [match["status"] for match in result["matches"]],
            ["matched", "matched", "unverified"],
        )
        self.assertEqual(
            [fact["origin"] for fact in result["trusted_facts"]],
            ["python_deterministic_match"] * 3,
        )
        self.assertIs(result["model_generated"], False)
        self.assertEqual(DEFAULT_JOBS_FILE.read_bytes(), jobs_before)
        self.assertEqual(DEFAULT_EVIDENCE_FILE.read_bytes(), evidence_before)


if __name__ == "__main__":
    unittest.main()
