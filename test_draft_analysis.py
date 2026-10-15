"""V1.9 草稿分析边界；仅使用虚构输入，不调用真实模型。"""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from file_import_server import create_import_app
from text_json_formatter import format_corrected_text, MAX_FORMAT_BODY
from test_text_json_formatter import payload, stub_client


HEADERS = {"Content-Type": "application/json", "X-CareerAgent-Import": "local-preview"}
ROUTE = "/imports/analyses"


def complete_draft():
    draft = format_corrected_text(payload(), client_factory=stub_client)["draft"]
    draft["job"]["requirements"].append({"requirement_id": "req_git", "skill_id": "git",
        "description": "虚构 Git 练习要求", "category": "required", "priority": 1})
    return draft


class DraftAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_import_app(), base_url="http://127.0.0.1:8002",
                                 client=("127.0.0.1", 50000))
        self.draft = complete_draft()

    def send(self, draft=None, **extra):
        return self.client.post(ROUTE, headers=HEADERS, json={
            "draft": self.draft if draft is None else draft, "analysis_confirmed": True, **extra})

    def test_complete_same_snapshot_is_unverified_and_missing_without_model_or_files(self):
        original = deepcopy(self.draft)
        paths = list(Path(".").glob("*.json")) + list(Path("examples").glob("*.json"))
        before = {path: path.read_bytes() for path in paths}
        with patch("text_json_formatter.create_qwen_client") as model, patch("file_import_server.extract_document") as parser, \
             patch("builtins.open", side_effect=AssertionError("分析不得打开文件")):
            response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()), {"report", "analysis_performed", "saved"})
        self.assertIs(response.json()["analysis_performed"], True)
        self.assertIs(response.json()["saved"], False)
        report = response.json()["report"]
        self.assertEqual(report["case"], original)
        self.assertEqual(self.draft, original)
        self.assertEqual([item["status"] for item in report["matches"]], ["unverified", "missing"])
        req = original["job"]["requirements"][0]
        ids = [original["candidate"]["evidence"][0]["evidence_id"]]
        self.assertEqual(report["matches"][0], {**req, "status": "unverified", "related_evidence_ids": ids})
        self.assertEqual(report["trusted_facts"], [
            {"requirement_id": req["requirement_id"], "skill_id": "python", "status": "unverified",
             "related_evidence_ids": ids, "verified_evidence_ids": [], "unverified_evidence_ids": ids,
             "origin": "python_deterministic_match"},
            {"requirement_id": "req_git", "skill_id": "git", "status": "missing",
             "related_evidence_ids": [], "verified_evidence_ids": [], "unverified_evidence_ids": [],
             "origin": "python_deterministic_match"}])
        self.assertEqual(report["verification"], {"applicable": False, "passed": None, "scope": "not_configured"})
        self.assertIs(report["model_generated"], False)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        model.assert_not_called(); parser.assert_not_called()
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_confirmation_is_required_and_must_be_true_bool(self):
        with patch("file_import_server.analyse_private_case") as runner:
            for value in [False, None, 1, "true", {}, []]:
                self.assertEqual(self.send(analysis_confirmed=value).status_code, 422)
            self.assertEqual(self.client.post(ROUTE, headers=HEADERS, json={"draft": self.draft}).status_code, 422)
        runner.assert_not_called()

    def test_missing_sections_block_analysis_but_remain_valid_partial_drafts(self):
        for keys in [("job",), ("candidate",), ("job", "candidate")]:
            draft = deepcopy(self.draft)
            for key in keys:
                draft[key] = None
            with patch("file_import_server.analyse_private_case") as runner:
                response = self.send(draft)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error_code"], "incomplete")
            runner.assert_not_called()
            self.assertEqual(self.client.post("/imports/validate-json", headers=HEADERS,
                                             json={"draft": draft}).status_code, 200)

    def test_no_overrides_paths_expected_output_or_unknown_fields(self):
        with patch("file_import_server.analyse_private_case") as runner:
            for field in ["path", "model", "output", "expected", "saved", "source_metadata"]:
                self.assertEqual(self.send(**{field: "private-value"}).status_code, 422)
                draft = deepcopy(self.draft); draft[field] = "private-value"
                response = self.send(draft)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("private-value", response.text)
        runner.assert_not_called()

    def test_all_evidence_flags_must_remain_false(self):
        with patch("file_import_server.analyse_private_case") as runner:
            for value in [True, 0, 1, None, "false"]:
                draft = deepcopy(self.draft); draft["candidate"]["evidence"][0]["verified"] = value
                self.assertEqual(self.send(draft).status_code, 422)
            for value in ["verified", True, None]:
                draft = deepcopy(self.draft)
                draft["qualifications"] = [{"qualification_id": "qual_001", "required": "模拟学历要求",
                    "declared": "未核实", "verification": value, "source": "虚构声明", "note": "不判断资格"}]
                self.assertEqual(self.send(draft).status_code, 422)
        runner.assert_not_called()

    def test_privacy_failure_never_echoes_input(self):
        self.draft["notice"] = "demo-private@example.com"
        with patch("file_import_server.analyse_private_case") as runner:
            response = self.send()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error_code"], "privacy")
        self.assertNotIn("example.com", response.text); runner.assert_not_called()

    def test_raw_duplicate_nonfinite_and_malformed_body_never_execute(self):
        raw = json.dumps(self.draft)
        bad = [raw.replace('{', '{"case_id":"other",', 1),
               raw.replace('"verified": false', '"verified": true,"verified": false'),
               raw.replace('"priority": 2', '"priority": 1e400'), "null", "[]", "{"]
        with patch("file_import_server.analyse_private_case") as runner:
            for text in bad:
                response = self.client.post(ROUTE, headers=HEADERS,
                    content=('{"draft":'+text+',"analysis_confirmed":true}').encode())
                self.assertEqual(response.status_code, 422)
        runner.assert_not_called()

    def test_local_same_origin_header_query_and_body_size_guards(self):
        body = {"draft": self.draft, "analysis_confirmed": True}
        with patch("file_import_server.analyse_private_case") as runner:
            self.assertEqual(self.client.post(ROUTE, json=body).status_code, 403)
            for extra in [{"Host": "localhost:8002"}, {"Origin": "https://evil.example"},
                          {"Sec-Fetch-Site": "cross-site"}, {"X-Forwarded-For": "127.0.0.1"}]:
                self.assertEqual(self.client.post(ROUTE, headers={**HEADERS, **extra}, json=body).status_code, 403)
            self.assertEqual(self.client.post(ROUTE+'?path=private-value', headers=HEADERS, json=body).status_code, 422)
            self.assertEqual(self.client.post(ROUTE, headers={**HEADERS, "Content-Type": "text/plain"}, json=body).status_code, 415)
            self.assertEqual(self.client.post(ROUTE, headers=HEADERS, content=b'x'*(MAX_FORMAT_BODY+1)).status_code, 413)
            remote = TestClient(create_import_app(), base_url="http://127.0.0.1:8002", client=("192.0.2.1", 50000))
            self.assertEqual(remote.post(ROUTE, headers=HEADERS, json=body).status_code, 403)
        runner.assert_not_called()

    def test_internal_error_is_fixed_and_retry_can_recover(self):
        with patch("file_import_server.analyse_private_case", side_effect=RuntimeError("private-path secret-content")):
            response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "analysis")
        self.assertNotIn("secret", response.text); self.assertNotIn("private-path", response.text)
        self.assertEqual(self.send().status_code, 200)

    def test_empty_evidence_produces_missing_not_a_real_world_ability_denial(self):
        self.draft["candidate"]["evidence"] = []
        report = self.send().json()["report"]
        self.assertEqual([item["status"] for item in report["matches"]], ["missing", "missing"])

    def test_second_request_uses_edited_snapshot_without_affecting_prior_result(self):
        first = self.send().json()
        self.draft["candidate"]["evidence"][0]["skill_id"] = "git"
        self.draft["qualifications"] = [{"qualification_id": "qual_001", "required": "模拟学历要求",
            "declared": "未核实", "verification": "unverified", "source": "虚构声明", "note": "不判断资格"}]
        second = self.send().json()
        self.assertEqual([item["status"] for item in second["report"]["matches"]], ["missing", "unverified"])
        self.assertEqual(first["report"]["matches"][0]["status"], "unverified")
        self.assertEqual(second["report"]["case"]["qualifications"], self.draft["qualifications"])


if __name__ == "__main__":
    unittest.main()
