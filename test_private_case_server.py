"""私有页面只使用人工资料测试，不读取实际简历或私人案例。"""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from private_case_runner import PrivateCaseError, analyse_private_case
from private_case_server import create_private_app, main
from test_private_case_runner import synthetic_case


def client_for(app, **kwargs):
    return TestClient(app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 50000), **kwargs)


HEADERS = {"X-CareerAgent-Private": "local-readonly"}


class PrivateServerTests(unittest.TestCase):
    def setUp(self):
        self.case = synthetic_case()
        self.app = create_private_app(self.case)
        self.client = client_for(self.app)

    def loaded(self):
        return self.client.get("/private/case", headers=HEADERS).json()

    def test_same_snapshot_is_used_for_inputs_and_analysis(self):
        loaded = self.loaded()
        response = self.client.post("/private/analyses", json={"snapshot_id": loaded["snapshot_id"]}, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["snapshot_id"], loaded["snapshot_id"])
        self.assertEqual(response.json()["report"], analyse_private_case(loaded["case"]))
        self.assertEqual(loaded["case"], self.case)

    def test_input_and_response_changes_cannot_mutate_server_snapshot(self):
        original = deepcopy(self.case)
        self.case["candidate"]["evidence"].clear()
        loaded = self.loaded()
        loaded["case"]["candidate"]["evidence"].clear()
        self.assertEqual(self.loaded()["case"], original)

    def test_page_has_no_data_upload_or_external_dependencies(self):
        response = self.client.get("/private")
        self.assertEqual(response.status_code, 200)
        self.assertIn("分析这份资料", response.text)
        self.assertNotIn("innerHTML", response.text)
        self.assertNotIn("<script src=", response.text)
        self.assertNotIn("人工测试声明", response.text)
        self.assertNotIn('type="file"', response.text)

    def test_extra_client_fields_rejected_without_echo(self):
        snapshot_id = self.loaded()["snapshot_id"]
        with patch("private_case_server.analyse_private_case") as analyser:
            for key in ["case_file", "candidate", "job", "model", "output_file"]:
                response = self.client.post("/private/analyses", headers=HEADERS, json={"snapshot_id": snapshot_id, key: "private-request-value"})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": "请求参数无效。"})
                self.assertNotIn("private-request-value", response.text)
        analyser.assert_not_called()

    def test_invalid_snapshot_types_and_malformed_json_rejected(self):
        for value in [None, True, 12, {}, "short", "A" * 64]:
            with self.subTest(value=value):
                self.assertEqual(self.client.post("/private/analyses", headers=HEADERS, json={"snapshot_id": value}).status_code, 422)
        response = self.client.post("/private/analyses", headers={**HEADERS, "Content-Type": "application/json"}, content="{private-broken")
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("private-broken", response.text)

    def test_query_parameters_rejected_before_analysis(self):
        with patch("private_case_server.analyse_private_case") as analyser:
            self.assertEqual(self.client.get("/private?file=private-value").status_code, 422)
            self.assertEqual(self.client.get("/private/case?case_file=private-value", headers=HEADERS).status_code, 422)
            self.assertEqual(self.client.post("/private/analyses?model=other", headers=HEADERS, json={"snapshot_id": self.loaded()["snapshot_id"]}).status_code, 422)
        analyser.assert_not_called()

    def test_wrong_snapshot_returns_conflict_without_execution(self):
        with patch("private_case_server.analyse_private_case") as analyser:
            response = self.client.post("/private/analyses", headers=HEADERS, json={"snapshot_id": "0" * 64})
        self.assertEqual(response.status_code, 409)
        analyser.assert_not_called()

    def test_private_data_requires_same_origin_custom_header(self):
        self.assertEqual(self.client.get("/private/case").status_code, 403)
        self.assertEqual(self.client.post("/private/analyses", json={"snapshot_id": self.loaded()["snapshot_id"]}).status_code, 403)
        self.assertEqual(self.client.get("/private/case", headers={"X-CareerAgent-Private": "wrong"}).status_code, 403)

    def test_non_loopback_clients_cannot_read_page_or_data(self):
        remote = TestClient(self.app, base_url="http://127.0.0.1:8001", client=("192.0.2.1", 50000))
        for route in ["/private", "/private/case"]:
            self.assertEqual(remote.get(route, headers=HEADERS).status_code, 403)

    def test_alternate_hosts_and_ports_rejected(self):
        for host in ["evil.example", "localhost:8001", "127.0.0.1:8002"]:
            with self.subTest(host=host):
                self.assertEqual(self.client.get("/private/case", headers={**HEADERS, "Host": host}).status_code, 403)

    def test_external_origins_fetch_sites_and_preflight_rejected(self):
        for extra in [{"Origin": "http://evil.example"}, {"Origin": "null"}, {"Origin": "http://127.0.0.1:8002"}, {"Sec-Fetch-Site": "cross-site"}]:
            with self.subTest(extra=extra):
                self.assertEqual(self.client.get("/private/case", headers={**HEADERS, **extra}).status_code, 403)
        response = self.client.options("/private/analyses", headers={"Origin": "http://evil.example", "Access-Control-Request-Headers": "x-careeragent-private"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("access-control-allow-origin", response.headers)
        self.assertEqual(self.client.get("/private/case", headers={**HEADERS, "Origin": "http://127.0.0.1:8001", "Sec-Fetch-Site": "same-origin"}).status_code, 200)

    def test_proxy_headers_are_not_trusted(self):
        for header in ["Forwarded", "X-Forwarded-For", "X-Forwarded-Host"]:
            self.assertEqual(self.client.get("/private/case", headers={**HEADERS, header: "127.0.0.1"}).status_code, 403)

    def test_private_cache_and_embedding_headers_on_success_and_errors(self):
        for response in [self.client.get("/private"), self.client.get("/private/case", headers=HEADERS), self.client.get("/private/case")]:
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
            self.assertEqual(response.headers["x-frame-options"], "DENY")
            self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_missing_page_returns_safe_error(self):
        with patch("private_case_server.PRIVATE_PAGE_FILE", Path("private-not-found.html")):
            response = self.client.get("/private")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-not-found", response.text)

    def test_analysis_failure_does_not_return_private_exception(self):
        with patch("private_case_server.analyse_private_case", side_effect=PrivateCaseError("private-debug-value")):
            response = self.client.post("/private/analyses", headers=HEADERS, json={"snapshot_id": self.loaded()["snapshot_id"]})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-debug-value", response.text)

    def test_unsafe_case_rejected_before_app_is_created(self):
        case = synthetic_case()
        case["candidate"]["evidence"][0]["source"] = "demo@example.test"
        with self.assertRaises(PrivateCaseError):
            create_private_app(case)

    def test_normal_unicode_round_trips_through_private_http(self):
        text = "中文与表情 🐱\t第一行\n第二行\r\n第三行"
        case = synthetic_case()
        case["job"]["title"] = text
        case["candidate"]["evidence"][0]["description"] = text
        client = client_for(create_private_app(case))
        loaded = client.get("/private/case", headers=HEADERS).json()
        response = client.post("/private/analyses", headers=HEADERS, json={"snapshot_id": loaded["snapshot_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loaded["case"], case)
        self.assertEqual(response.json()["report"]["case"], case)
        self.assertTrue(response.json()["report"]["verification"]["passed"])

    def test_public_app_and_private_schema_are_isolated(self):
        from api_app import app as public_app
        self.assertEqual(TestClient(public_app).get("/private/case").status_code, 404)
        for route in ["/demo", "/analyses", "/docs", "/openapi.json"]:
            self.assertEqual(self.client.get(route).status_code, 404)

    def test_snapshot_is_not_reloaded_from_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps(self.case), encoding="utf-8")
            from private_case_runner import load_private_case
            client = client_for(create_private_app(load_private_case(path)))
            before = client.get("/private/case", headers=HEADERS).json()
            changed = deepcopy(self.case)
            changed["candidate"]["evidence"].clear()
            path.write_text(json.dumps(changed), encoding="utf-8")
            self.assertEqual(client.get("/private/case", headers=HEADERS).json(), before)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), changed)


class PrivateLauncherTests(unittest.TestCase):
    def test_invalid_text_file_rejected_without_starting_or_echoing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            for value in [chr(0xd800), chr(0xdfff), chr(27) + "[2J", chr(0x9b) + "2J", "\roverwrite"]:
                case = synthetic_case()
                case["job"]["title"] = "private-invalid-text" + value
                path.write_text(json.dumps(case), encoding="utf-8")
                before = path.read_bytes()
                with self.assertRaises(PrivateCaseError):
                    create_private_app(case)
                output, errors = io.StringIO(), io.StringIO()
                with patch("private_case_server.uvicorn.run") as server, redirect_stdout(output), redirect_stderr(errors):
                    self.assertEqual(main(["--case-file", str(path)]), 2)
                server.assert_not_called()
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("private-invalid-text", errors.getvalue())
                self.assertNotIn(str(path), errors.getvalue())
                self.assertNotIn("Traceback", errors.getvalue())
                self.assertNotIn(value, errors.getvalue())
                errors.getvalue().encode("utf-8")
                self.assertEqual(path.read_bytes(), before)

    def test_launcher_binds_only_loopback_without_private_access_logs(self):
        with patch("private_case_server.load_private_case", return_value=synthetic_case()), patch("private_case_server.uvicorn.run") as server, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--case-file", "private-case.json"]), 0)
        self.assertEqual(server.call_args.kwargs["host"], "127.0.0.1")
        self.assertFalse(server.call_args.kwargs["access_log"])
        self.assertFalse(server.call_args.kwargs["proxy_headers"])
        self.assertNotIn("private-case.json", output.getvalue())

    def test_bad_arguments_paths_and_ports_do_not_start_or_echo(self):
        for arguments in [[], ["--case-file", "not-found-private.json"], ["--case-file", "private.json", "--host", "0.0.0.0"], ["--case-file", "private.json", "--port", "not-a-port"]]:
            errors = io.StringIO()
            with patch("private_case_server.uvicorn.run") as server, redirect_stderr(errors):
                self.assertEqual(main(arguments), 2)
            server.assert_not_called()
            self.assertNotIn("not-found-private", errors.getvalue())
            self.assertNotIn("0.0.0.0", errors.getvalue())
        for port in [0, True, -1, 65536]:
            with self.subTest(port=port), self.assertRaises(PrivateCaseError):
                create_private_app(synthetic_case(), port=port)


if __name__ == "__main__":
    unittest.main()
