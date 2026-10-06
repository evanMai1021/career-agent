"""历史资料的完整演示字段、范围限制和不变性检查。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_app import app, create_app, DEFAULT_USERS_FILE, DEFAULT_PROGRESS_FILE, DEFAULT_EVIDENCE_FILE
from demo_profile import load_demo_profile


class DemoProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {
            "users_file": self.root / "users.json",
            "progress_file": self.root / "study_progress.json",
            "evidence_file": self.root / "candidate_evidence.json",
        }
        for key, source in [("users_file", DEFAULT_USERS_FILE), ("progress_file", DEFAULT_PROGRESS_FILE), ("evidence_file", DEFAULT_EVIDENCE_FILE)]:
            self.paths[key].write_bytes(source.read_bytes())
        self.client = TestClient(create_app(**self.paths))

    def test_full_known_history_matches_source_without_writes(self):
        before = {key: path.read_bytes() for key, path in self.paths.items()}
        response = self.client.get("/demo/profile")
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["username"], "test_user")
        self.assertEqual(profile["data_kind"], "historical_demo")
        self.assertEqual(profile["target_role"], "AI Agent开发")
        self.assertEqual(profile["study_progress"], json.loads(before["progress_file"])["test_user"])
        self.assertEqual(profile["evidence"], json.loads(before["evidence_file"])["candidates"][0]["evidence"])
        self.assertEqual(before, {key: path.read_bytes() for key, path in self.paths.items()})

    def test_groups_preserve_verification_and_do_not_promote_learning(self):
        profile = load_demo_profile(**self.paths)
        self.assertEqual(profile["evidence_groups"]["verified_application"], ["ev_python_tests", "ev_agent_tool_calling"])
        self.assertEqual(profile["evidence_groups"]["verified_learning"], [])
        self.assertEqual(profile["evidence_groups"]["unverified"], ["ev_fastapi_plan"])
        self.assertIn("106", profile["study_progress"]["agent_progress"])
        self.assertFalse(profile["evidence"][-1]["verified"])

    def test_verified_practice_is_separate_from_project_evidence(self):
        data = json.loads(self.paths["evidence_file"].read_text(encoding="utf-8"))
        item = data["candidates"][0]["evidence"][-1]
        item.update(verified=True, level="practice")
        self.paths["evidence_file"].write_text(json.dumps(data), encoding="utf-8")
        profile = load_demo_profile(**self.paths)
        self.assertEqual(profile["evidence_groups"]["verified_learning"], ["ev_fastapi_plan"])
        self.assertNotIn("ev_fastapi_plan", profile["evidence_groups"]["verified_application"])

    def test_only_public_demo_fields_and_fixed_user_are_returned(self):
        users = {"test_user": {"target_role": "测试岗位", "private_field": "hidden-value"}, "other_user": {"target_role": "other-private"}}
        self.paths["users_file"].write_text(json.dumps(users), encoding="utf-8")
        response = self.client.get("/demo/profile")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("hidden-value", response.text)
        self.assertNotIn("other-private", response.text)
        self.assertNotIn(str(self.root), response.text)

    def test_missing_file_returns_safe_503_without_creating_it(self):
        for key in self.paths:
            with self.subTest(key=key):
                paths = dict(self.paths)
                paths[key] = self.root / ("missing-" + key + ".json")
                response = TestClient(create_app(**paths)).get("/demo/profile")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "历史用户资料暂不可用。"})
                self.assertNotIn(str(self.root), response.text)
                self.assertFalse(paths[key].exists())

    def test_invalid_json_or_encoding_returns_safe_503(self):
        for content in [b"{broken", b"\xff"]:
            with self.subTest(content=content):
                self.paths["users_file"].write_bytes(content)
                response = self.client.get("/demo/profile")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(str(self.root), response.text)

    def test_empty_or_missing_target_role_is_rejected(self):
        for user in [{}, {"target_role": " "}, {"target_role": False}]:
            with self.subTest(user=user):
                self.paths["users_file"].write_text(json.dumps({"test_user": user}), encoding="utf-8")
                self.assertEqual(self.client.get("/demo/profile").status_code, 503)

    def test_empty_evidence_stays_empty_not_inferred_from_progress(self):
        self.paths["evidence_file"].write_text(json.dumps({"candidates": [{"username": "test_user", "evidence": []}]}), encoding="utf-8")
        profile = load_demo_profile(**self.paths)
        self.assertEqual(profile["evidence"], [])
        self.assertTrue(all(not items for items in profile["evidence_groups"].values()))
        self.assertIn("agent_progress", profile["study_progress"])

    def test_query_parameters_are_rejected_before_reading(self):
        with patch("api_app.load_demo_profile") as reader:
            for query in ["username=other_user", "users_file=.env", "model=other"]:
                self.assertEqual(self.client.get("/demo/profile?" + query).status_code, 422)
        reader.assert_not_called()

    def test_extra_evidence_fields_are_rejected_without_leaking(self):
        data = json.loads(self.paths["evidence_file"].read_text(encoding="utf-8"))
        data["candidates"][0]["evidence"][0]["private_field"] = "private-demo-value"
        self.paths["evidence_file"].write_text(json.dumps(data), encoding="utf-8")
        response = self.client.get("/demo/profile")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-demo-value", response.text)


if __name__ == "__main__":
    unittest.main()
