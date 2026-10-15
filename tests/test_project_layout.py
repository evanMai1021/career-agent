"""目录迁移后的入口、资源与数据保护回归；不调用真实模型。"""

import importlib
from pathlib import Path
import subprocess
import sys
import unittest

from career_agent.paths import PROJECT_ROOT, WEB_ROOT
from career_agent.services import api_app, file_import_server, private_case_server
from career_agent.evaluation.job_analysis_evaluation_runner import save_evaluation_report


class ProjectLayoutTests(unittest.TestCase):
    def test_root_entrypoints_reuse_exact_implementation_module(self):
        modules = {
            "main": "career_agent.cli.main",
            "api_app": "career_agent.services.api_app",
            "file_import_server": "career_agent.services.file_import_server",
            "private_case_runner": "career_agent.services.private_case_runner",
            "private_case_server": "career_agent.services.private_case_server",
            "job_analysis_evaluation_runner": "career_agent.evaluation.job_analysis_evaluation_runner",
        }
        for legacy, canonical in modules.items():
            with self.subTest(entry=legacy):
                self.assertIs(importlib.import_module(legacy), importlib.import_module(canonical))

    def test_resource_locations_keep_data_in_root_and_pages_in_web(self):
        self.assertEqual(PROJECT_ROOT, Path(__file__).resolve().parents[1])
        for resource in [api_app.DEFAULT_JOBS_FILE, api_app.DEFAULT_EVIDENCE_FILE,
                         api_app.DEFAULT_USERS_FILE, api_app.DEFAULT_PROGRESS_FILE]:
            self.assertEqual(resource.parent, PROJECT_ROOT)
            self.assertTrue(resource.is_file())
        for resource in [api_app.DEMO_PAGE_FILE, file_import_server.PAGE_FILE,
                         private_case_server.PRIVATE_PAGE_FILE]:
            self.assertEqual(resource.parent, WEB_ROOT)
            self.assertTrue(resource.is_file())

    def test_original_cli_help_remains_runnable(self):
        for entry in ["file_import_server.py", "private_case_server.py",
                      "private_case_runner.py", "job_analysis_evaluation_runner.py"]:
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, "-X", "utf8", entry, "--help"],
                                        cwd=PROJECT_ROOT, capture_output=True, encoding="utf-8", timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--help", result.stdout)

    def test_default_report_protection_still_targets_original_data(self):
        target = PROJECT_ROOT / "users.json"
        before = target.read_bytes()
        result = save_evaluation_report({"summary": {}}, target)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "不能覆盖项目数据文件。")
        self.assertEqual(target.read_bytes(), before)

    def test_importing_package_does_not_start_services_or_load_model_client(self):
        code = ("import sys; import career_agent; "
                "assert not any(name.startswith(('career_agent.services.', 'career_agent.agents.')) "
                "for name in sys.modules)")
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                                cwd=PROJECT_ROOT, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
