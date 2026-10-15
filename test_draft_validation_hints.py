"""V1.9.1 固定字段定位；仅用虚构输入，不调用真实 API。"""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from draft_validation_hints import draft_field_errors
from test_draft_analysis import complete_draft, HEADERS, ROUTE
from text_json_formatter import FormatError, validate_draft
from fastapi.testclient import TestClient
from file_import_server import create_import_app


class DraftHintsTests(unittest.TestCase):
    def setUp(self):
        self.draft = complete_draft()
        self.client = TestClient(create_import_app(), base_url="http://127.0.0.1:8002", client=("127.0.0.1", 50000))

    def errors(self, draft):
        with self.assertRaises(FormatError) as error:
            validate_draft(draft)
        self.assertEqual(error.exception.code, "json")
        return error.exception.field_errors

    def test_priority_points_to_fixed_index_without_echoing_value(self):
        self.draft["job"]["requirements"][1]["priority"] = "private-value"
        errors = self.errors(self.draft)
        self.assertIn({"path": "job.requirements[1].priority", "reason": "priority"}, errors)
        self.assertNotIn("private-value", json.dumps(errors))

    def test_types_categories_levels_and_false_only_are_localized(self):
        changes = [("job", "requirements", "category", [], "category"),
                   ("job", "requirements", "priority", True, "priority"),
                   ("candidate", "evidence", "level", {}, "level"),
                   ("candidate", "evidence", "verified", 0, "false_only")]
        for section, collection, field, value, reason in changes:
            draft = deepcopy(self.draft); draft[section][collection][0][field] = value
            self.assertIn({"path": f"{section}.{collection}[0].{field}", "reason": reason}, self.errors(draft))

    def test_unknown_keys_and_values_never_appear_in_hint(self):
        self.draft["job"]["requirements"][0]["unknown-private-field"] = "unknown-private-content"
        errors = self.errors(self.draft)
        self.assertIn({"path": "job.requirements[0]", "reason": "fields"}, errors)
        self.assertNotIn("unknown-private", json.dumps(errors))

    def test_missing_fields_identifiers_and_duplicates(self):
        del self.draft["job"]["title"]
        self.draft["case_id"] = "Not_Anonymous"
        self.draft["job"]["requirements"][1]["requirement_id"] = self.draft["job"]["requirements"][0]["requirement_id"]
        errors = self.errors(self.draft)
        for item in [{"path": "job.title", "reason": "text"}, {"path": "case_id", "reason": "identifier"},
                     {"path": "job.requirements[1].requirement_id", "reason": "duplicate"}]:
            self.assertIn(item, errors)

    def test_qualification_verification_and_row_shapes(self):
        self.draft["qualifications"] = [{"qualification_id": "qual_001", "required": "虚构要求",
            "declared": "虚构声明", "source": "模拟来源", "verification": "verified", "note": "待核实"}]
        self.assertIn({"path": "qualifications[0].verification", "reason": "unverified_only"}, self.errors(self.draft))
        self.draft["qualifications"] = [None]
        self.assertIn({"path": "qualifications[0]", "reason": "object"}, self.errors(self.draft))

    def test_empty_and_oversized_collections_are_bounded(self):
        self.draft["job"]["requirements"] = []
        self.assertIn({"path": "job.requirements", "reason": "list"}, self.errors(self.draft))
        self.draft = complete_draft(); self.draft["candidate"]["evidence"] = [None]*61
        errors = self.errors(self.draft)
        self.assertIn({"path": "candidate.evidence", "reason": "limit"}, errors)
        self.assertLessEqual(len(errors), 8)
        self.assertTrue(all("private" not in item["path"] for item in errors))

    def test_privacy_wins_over_schema_errors_without_locations_or_echo(self):
        self.draft["notice"] = "fiction-private@example.com"
        self.draft["job"]["requirements"][0]["priority"] = False
        with patch("text_json_formatter.create_qwen_client") as model:
            for route, body in [("/imports/validate-json", {"draft": self.draft}),
                                (ROUTE, {"draft": self.draft, "analysis_confirmed": True})]:
                response = self.client.post(route, headers=HEADERS, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error_code"], "privacy")
                self.assertNotIn("field_errors", response.json())
                self.assertNotIn("example.com", response.text)
        model.assert_not_called()

    def test_hints_on_validation_and_analysis_do_not_execute_analysis_or_model(self):
        self.draft["job"]["requirements"][0]["priority"] = False
        with patch("file_import_server.analyse_private_case") as analyse, patch("text_json_formatter.create_qwen_client") as model:
            for route, body in [("/imports/validate-json", {"draft": self.draft}),
                                (ROUTE, {"draft": self.draft, "analysis_confirmed": True})]:
                response = self.client.post(route, headers=HEADERS, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["field_errors"], [{"path": "job.requirements[0].priority", "reason": "priority"}])
                self.assertEqual(response.headers["cache-control"], "no-store")
        analyse.assert_not_called(); model.assert_not_called()

    def test_parser_errors_remain_generic_and_success_contract_unchanged(self):
        response = self.client.post("/imports/validate-json", headers=HEADERS, content=b'{"draft":{},"draft":{}}')
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("field_errors", response.json())
        original = deepcopy(self.draft)
        response = self.client.post("/imports/validate-json", headers=HEADERS, json={"draft": self.draft})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"], original)
        self.assertEqual(set(response.json()), {"draft", "schema_valid", "missing_sections", "verification", "analysis_performed", "saved"})
        self.assertEqual(self.draft, original)
        self.assertEqual(draft_field_errors(self.draft), [])
        self.draft["job"] = None
        self.assertEqual(draft_field_errors(self.draft), [])
        self.assertFalse(validate_draft(self.draft)["schema_valid"])


if __name__ == "__main__":
    unittest.main()
