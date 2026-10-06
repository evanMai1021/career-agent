"""模拟案例的独立预期、真实规则与只读接口测试。"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_app import app
from demo_cases import list_demo_cases, run_demo_case


class DemoCaseTests(unittest.TestCase):
    def test_four_states_follow_real_rule_functions(self):
        expected = {
            "verified_project": "matched", "verified_practice": "partial",
            "unverified_claim": "unverified", "no_evidence": "missing",
        }
        for case_id, state in expected.items():
            with self.subTest(case_id=case_id):
                report = run_demo_case(case_id)
                self.assertEqual(report["execution_status"], "completed")
                self.assertTrue(report["verification"]["passed"])
                self.assertEqual(report["analysis"]["matches"][0]["status"], state)
                self.assertEqual(report["analysis"]["trusted_facts"][0]["status"], state)
                self.assertIs(report["analysis"]["model_generated"], False)
                self.assertTrue(report["decisions"][0]["reason"])

    def test_invalid_evidence_is_rejected_before_matching(self):
        with patch("demo_cases.match_job_requirements") as matcher:
            report = run_demo_case("invalid_evidence")
        matcher.assert_not_called()
        self.assertEqual(report["execution_status"], "rejected")
        self.assertIsNone(report["analysis"])
        self.assertEqual(report["decisions"], [])
        self.assertIn("布尔值", report["error"])
        self.assertTrue(report["verification"]["passed"])

    def test_missing_evidence_is_completed_analysis_not_failure(self):
        report = run_demo_case("no_evidence")
        self.assertEqual(report["execution_status"], "completed")
        self.assertEqual(report["analysis"]["trusted_facts"][0]["related_evidence_ids"], [])
        self.assertTrue(report["verification"]["passed"])

    def test_unverified_project_does_not_become_verified_fact(self):
        fact = run_demo_case("unverified_claim")["analysis"]["trusted_facts"][0]
        self.assertEqual(fact["verified_evidence_ids"], [])
        self.assertEqual(fact["unverified_evidence_ids"], ["ev_csv_script"])

    def test_expected_states_are_independent_from_actual_result(self):
        from demo_cases import _CASES
        changed = list_demo_cases()[0]
        changed["expected"]["states"][0]["status"] = "missing"
        with patch.dict(_CASES, {"verified_project": changed}):
            report = run_demo_case("verified_project")
        self.assertEqual(report["analysis"]["matches"][0]["status"], "matched")
        self.assertFalse(report["verification"]["passed"])

    def test_returned_inputs_do_not_mutate_case_registry(self):
        cases = list_demo_cases()
        cases[0]["candidate"]["evidence"][0]["verified"] = False
        report = run_demo_case("verified_project")
        report["case"]["candidate"]["evidence"].clear()
        self.assertEqual(run_demo_case("verified_project")["analysis"]["matches"][0]["status"], "matched")

    def test_shared_production_error_does_not_change_independent_expectation(self):
        wrong_matches = run_demo_case("verified_project")["analysis"]["matches"]
        wrong_matches[0]["status"] = "partial"
        with patch("demo_cases.match_job_requirements", return_value=wrong_matches), \
                patch("demo_cases.build_trusted_facts", return_value=[]):
            report = run_demo_case("verified_project")
        self.assertEqual(report["case"]["expected"]["states"][0]["status"], "matched")
        self.assertFalse(report["verification"]["passed"])

    def test_fact_omission_tampering_or_extra_text_cannot_pass(self):
        from copy import deepcopy
        facts = run_demo_case("verified_project")["analysis"]["trusted_facts"]
        wrong_ids = deepcopy(facts)
        wrong_ids[0]["verified_evidence_ids"] = ["unknown"]
        extra_text = deepcopy(facts)
        extra_text[0]["claim"] = "unsupported-demo-claim"
        for altered in [[], wrong_ids, extra_text]:
            with self.subTest(altered=altered):
                with patch("demo_cases.build_trusted_facts", return_value=altered):
                    report = run_demo_case("verified_project")
                self.assertFalse(report["verification"]["passed"])

    def test_match_evidence_ids_cannot_pass_using_only_same_status(self):
        matches = run_demo_case("verified_project")["analysis"]["matches"]
        matches[0]["related_evidence_ids"] = []
        facts = run_demo_case("verified_project")["analysis"]["trusted_facts"]
        with patch("demo_cases.match_job_requirements", return_value=matches), \
                patch("demo_cases.build_trusted_facts", return_value=facts):
            self.assertFalse(run_demo_case("verified_project")["verification"]["passed"])


class DemoCaseEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalogue_contains_only_five_explicit_simulated_inputs(self):
        response = self.client.get("/demo/cases")
        self.assertEqual(response.status_code, 200)
        cases = response.json()
        self.assertEqual(len(cases), 5)
        self.assertTrue(all(case["data_kind"] == "synthetic_demo" for case in cases))
        self.assertEqual({case["job"]["job_id"] for case in cases}, {"demo_csv_assistant"})
        self.assertEqual(cases[-1]["candidate"]["evidence"][0]["verified"], "true")

    def test_reports_distinguish_execution_from_case_verification(self):
        for case in list_demo_cases():
            with self.subTest(case_id=case["case_id"]):
                response = self.client.post("/demo/analyses", json={"case_id": case["case_id"]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), run_demo_case(case["case_id"]))

    def test_rejects_unknown_wrong_type_or_client_supplied_inputs(self):
        payloads = [{"case_id": value} for value in ["", "unknown", True, {}, 1]]
        payloads += [{"case_id": "verified_project", key: ".env"}
                     for key in ["jobs_file", "candidate", "model", "output_file"]]
        with patch("api_app.run_demo_case") as runner:
            for payload in payloads:
                with self.subTest(payload=payload):
                    self.assertEqual(self.client.post("/demo/analyses", json=payload).status_code, 422)
        runner.assert_not_called()

    def test_rejects_query_parameters_for_both_endpoints(self):
        self.assertEqual(self.client.get("/demo/cases?file=.env").status_code, 422)
        self.assertEqual(self.client.post("/demo/analyses?model=other", json={"case_id": "verified_project"}).status_code, 422)

    def test_internal_error_is_not_reported_as_expected_rejection(self):
        with patch("demo_cases.build_trusted_facts", side_effect=ValueError("private-path")):
            response = self.client.post("/demo/analyses", json={"case_id": "verified_project"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-path", response.text)


if __name__ == "__main__":
    unittest.main()
