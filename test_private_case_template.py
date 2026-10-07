"""公开模板只含虚构资料；用独立预设验证真实入口，不读取私人文件。"""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from evaluation_privacy import find_sensitive_kinds
from private_case_runner import analyse_private_case, load_private_case, main, run_private_case_file
from private_case_server import create_private_app


TEMPLATE = Path(__file__).resolve().parent / "examples" / "careeragent_v1_7_private_case_template.json"
EXPECTED_STATES = [
    {"requirement_id": "req_python", "status": "matched"},
    {"requirement_id": "req_sql", "status": "partial"},
    {"requirement_id": "req_linux", "status": "unverified"},
    {"requirement_id": "req_git", "status": "missing"},
]


class PrivateTemplateTests(unittest.TestCase):
    def test_published_template_is_synthetic_complete_and_read_only(self):
        before = TEMPLATE.read_bytes()
        case = load_private_case(TEMPLATE)
        self.assertEqual(case["data_kind"], "synthetic_private_test")
        self.assertIn("纯虚构", case["notice"])
        self.assertEqual(find_sensitive_kinds(case), [])
        self.assertEqual(case["expected"]["states"], EXPECTED_STATES)
        report = run_private_case_file(TEMPLATE)
        self.assertTrue(report["verification"]["passed"])
        self.assertFalse(report["model_generated"])
        self.assertEqual(len(report["trusted_facts"]), 4)
        self.assertEqual(
            [{"requirement_id": item["requirement_id"], "status": item["status"]} for item in report["matches"]],
            EXPECTED_STATES,
        )
        self.assertEqual(report["trusted_facts"][0]["verified_evidence_ids"], ["ev_python_project"])
        self.assertEqual(report["trusted_facts"][2]["unverified_evidence_ids"], ["ev_linux_claim"])
        self.assertEqual(report["trusted_facts"][3]["related_evidence_ids"], [])
        self.assertEqual(TEMPLATE.read_bytes(), before)

    def test_documented_cli_accepts_template_in_both_modes(self):
        before = TEMPLATE.read_bytes()
        for flags in [[], ["--json"]]:
            output = io.StringIO()
            with self.subTest(flags=flags), redirect_stdout(output):
                self.assertEqual(main(["--case-file", str(TEMPLATE), *flags]), 0)
            if flags:
                self.assertTrue(json.loads(output.getvalue())["verification"]["passed"])
            else:
                self.assertIn("纯虚构", output.getvalue())
                for label in ["已匹配", "部分匹配", "待核实", "缺少证据"]:
                    self.assertIn(f"{label}：1", output.getvalue())
                self.assertIn("ev_swift_other / swift", output.getvalue())
            self.assertNotIn(str(TEMPLATE), output.getvalue())
        self.assertEqual(TEMPLATE.read_bytes(), before)

    def test_resetting_markers_and_removing_demo_preset_does_not_prove_claims(self):
        original = load_private_case(TEMPLATE)
        case = deepcopy(original)
        case.pop("expected")
        for item in case["candidate"]["evidence"]:
            item["verified"] = False
        report = analyse_private_case(case)
        self.assertEqual([item["status"] for item in report["matches"]], ["unverified", "unverified", "unverified", "missing"])
        self.assertFalse(report["verification"]["applicable"])
        self.assertIsNone(report["verification"]["passed"])
        self.assertTrue(all(not item["verified_evidence_ids"] for item in report["trusted_facts"]))
        self.assertEqual(load_private_case(TEMPLATE), original)

    def test_template_works_with_private_http_snapshot_without_listening(self):
        case = load_private_case(TEMPLATE)
        client = TestClient(create_private_app(case), base_url="http://127.0.0.1:8001", client=("127.0.0.1", 50000))
        headers = {"X-CareerAgent-Private": "local-readonly"}
        loaded = client.get("/private/case", headers=headers).json()
        self.assertEqual(loaded["case"], case)
        response = client.post("/private/analyses", headers=headers, json={"snapshot_id": loaded["snapshot_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["snapshot_id"], loaded["snapshot_id"])
        self.assertEqual(response.json()["report"], analyse_private_case(case))


if __name__ == "__main__":
    unittest.main()
