"""统一启动器的虚构配置、进程替身和本机真实 HTTP 测试；不调用模型。"""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from career_agent.cli import start_services as launcher
from career_agent.paths import PROJECT_ROOT
from career_agent.services import managed_worker


def arguments(**changes):
    values = dict(demo_port=8000, import_port=8002, private_port=8001,
                  case_file=None, enable_model_format=False)
    return SimpleNamespace(**(values | changes))


def fake_child(spec, *, ready=True, status=None):
    process = Mock()
    process.poll.return_value = status
    process.stdin = io.StringIO()
    process.stdout = io.StringIO(launcher.READY_MARKER + "\n" if ready else "")
    child = launcher.OwnedChild(spec, process, threading.Event())
    if ready:
        child.ready.set()
    return child


class LauncherTests(unittest.TestCase):
    def test_default_plan_has_two_services_and_never_selects_private_file(self):
        plan = launcher.build_plan(arguments())
        self.assertEqual([spec.key for spec in plan], ["demo", "import"])
        self.assertTrue(all(spec.case_file is None and not spec.enable_model_format for spec in plan))

    def test_explicit_case_and_model_switch_are_not_inferred(self):
        plan = launcher.build_plan(arguments(case_file="examples/careeragent_v1_7_private_case_template.json",
                                            enable_model_format=True))
        self.assertEqual(len(plan), 3)
        self.assertTrue(Path(plan[2].case_file).is_absolute())
        self.assertTrue(plan[1].enable_model_format)
        self.assertFalse(plan[0].enable_model_format)

    def test_invalid_ports_and_enabled_duplicate_ports_are_rejected(self):
        for changes in [dict(demo_port=True), dict(import_port=0), dict(private_port=65536),
                        dict(demo_port=8002), dict(case_file=" "),
                        dict(case_file="synthetic.json", private_port=8000)]:
            with self.subTest(changes=changes), self.assertRaises(launcher.LaunchError):
                launcher.build_plan(arguments(**changes))
        self.assertEqual(len(launcher.build_plan(arguments(private_port=8000))), 2)

    def test_command_uses_current_interpreter_and_argument_list_without_shell(self):
        spec = launcher.ServiceSpec("private", "私有资料页", 8031, "/private", "folder with space/case.json")
        command = launcher.child_command(spec)
        self.assertEqual(command[0], launcher.sys.executable)
        self.assertEqual(command[-2:], ["--case-file", "folder with space/case.json"])
        self.assertNotIn("--enable-model-format", command)

    def test_model_switch_only_added_when_explicit(self):
        plan = launcher.build_plan(arguments(enable_model_format=True))
        self.assertIn("--enable-model-format", launcher.child_command(plan[1]))
        self.assertNotIn("--enable-model-format", launcher.child_command(plan[0]))

    def test_child_has_fixed_working_directory_hidden_window_and_private_output(self):
        spec = launcher.build_plan(arguments())[0]
        with patch.object(launcher.subprocess, "Popen") as factory:
            launcher.start_child(spec)
        kwargs = factory.call_args.kwargs
        self.assertEqual(kwargs["cwd"], PROJECT_ROOT)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdin"], subprocess.PIPE)
        self.assertNotIn("shell", kwargs)

    def test_occupied_port_starts_nothing_and_preserves_existing_listener(self):
        with socket.socket() as existing:
            existing.bind(("127.0.0.1", 0))
            existing.listen()
            spec = launcher.ServiceSpec("demo", "演示页", existing.getsockname()[1], "/demo")
            with patch.object(launcher, "start_child") as start, redirect_stderr(io.StringIO()):
                self.assertEqual(launcher.run_services([spec], threading.Event()), 1)
            start.assert_not_called()
            self.assertGreaterEqual(existing.fileno(), 0)
            self.assertEqual(existing.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN), 1)

    def test_failed_second_spawn_cleans_only_first_owned_child_without_echo(self):
        plan = launcher.build_plan(arguments())
        owned = fake_child(plan[0])
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(launcher, "check_ports"), \
             patch.object(launcher, "start_child", side_effect=[owned, OSError("private-path secret")]), \
             patch.object(launcher, "stop_children", return_value=True) as cleanup, \
             redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(launcher.run_services(plan, threading.Event()), 1)
        self.assertEqual(cleanup.call_args.args[0], [owned])
        self.assertNotIn("均已就绪", output.getvalue())
        self.assertNotIn("private-path", errors.getvalue())

    def test_early_exit_is_not_ready_and_other_children_are_cleaned(self):
        plan = launcher.build_plan(arguments())
        children = [fake_child(plan[0], status=1), fake_child(plan[1])]
        with patch.object(launcher, "check_ports"), patch.object(launcher, "start_child", side_effect=children), \
             patch.object(launcher, "stop_children", return_value=True) as cleanup, \
             redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.run_services(plan, threading.Event()), 1)
        self.assertNotIn("均已就绪", output.getvalue())
        self.assertEqual(cleanup.call_args.args[0], children)

    def test_startup_timeout_never_prints_ready_urls(self):
        spec = launcher.build_plan(arguments())[0]
        with patch.object(launcher, "check_ports"), patch.object(launcher, "start_child", return_value=fake_child(spec, ready=False)), \
             patch.object(launcher, "stop_children", return_value=True), \
             redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.run_services([spec], threading.Event(), startup_seconds=0), 1)
        self.assertNotIn(spec.url, output.getvalue())
        self.assertIn("超时", errors.getvalue())

    def test_runtime_exit_stops_other_owned_services(self):
        spec = launcher.build_plan(arguments())[0]
        child = fake_child(spec)
        child.process.poll.side_effect = [None, 1]
        with patch.object(launcher, "check_ports"), patch.object(launcher, "start_child", return_value=child), \
             patch.object(launcher, "stop_children", return_value=True) as cleanup, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.run_services([spec], threading.Event()), 1)
        self.assertIn("已退出", errors.getvalue())
        self.assertEqual(cleanup.call_args.args[0], [child])

    def test_stop_requests_precede_wait_and_terminate_only_on_timeout(self):
        spec = launcher.build_plan(arguments())[0]
        child = fake_child(spec)
        child.process.poll.side_effect = [None, 0]
        child.process.wait.side_effect = [subprocess.TimeoutExpired("owned", 6), 0]
        with patch.object(child.process.stdin, "close"):
            self.assertTrue(launcher.stop_children([child]))
            self.assertEqual(child.process.stdin.getvalue(), "STOP\n")
        child.process.terminate.assert_called_once()
        child.process.kill.assert_not_called()

    def test_graceful_shutdown_does_not_terminate_or_kill(self):
        child = fake_child(launcher.build_plan(arguments())[0])
        child.process.poll.side_effect = [None, 0]
        self.assertTrue(launcher.stop_children([child]))
        child.process.terminate.assert_not_called()
        child.process.kill.assert_not_called()

    def test_forced_cleanup_is_limited_to_recorded_child(self):
        child = fake_child(launcher.build_plan(arguments())[0])
        child.process.poll.side_effect = [None, 0]
        child.process.wait.side_effect = [subprocess.TimeoutExpired("owned", 6), subprocess.TimeoutExpired("owned", 1), 0]
        self.assertTrue(launcher.stop_children([child]))
        child.process.kill.assert_called_once()

    def test_unconfirmed_shutdown_has_nonzero_result(self):
        stop = threading.Event()
        stop.set()
        with patch.object(launcher, "check_ports"), patch.object(launcher, "start_child") as start, \
             patch.object(launcher, "stop_children", return_value=False), \
             redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.run_services([], stop), 1)
        start.assert_not_called()
        self.assertIn("无法确认", errors.getvalue())

    def test_signal_context_requests_stop_and_restores_handlers(self):
        stop = threading.Event()
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        with launcher.shutdown_signals(stop):
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            self.assertTrue(stop.is_set())
        self.assertEqual({number: signal.getsignal(number) for number in before}, before)

    def test_main_defaults_and_private_errors_are_safe(self):
        with patch.object(launcher, "run_services", return_value=0) as run, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main([]), 0)
        self.assertEqual(len(run.call_args.args[0]), 2)
        self.assertIn("未配置，未启动", output.getvalue())
        self.assertIn("关闭；不需要密钥", output.getvalue())
        with patch.object(launcher, "run_services") as run, redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.main(["--demo-port", "private-secret-value"]), 2)
        run.assert_not_called()
        self.assertNotIn("private-secret-value", errors.getvalue())

    def test_worker_ready_marker_only_after_server_started(self):
        for started in (False, True):
            async def startup(server, sockets=None):
                server.started = started
            server = managed_worker.ReadyServer(managed_worker.uvicorn.Config("unused:app"))
            with patch.object(managed_worker.uvicorn.Server, "startup", new=startup), redirect_stdout(io.StringIO()) as output:
                asyncio.run(server.startup())
            self.assertEqual(launcher.READY_MARKER in output.getvalue(), started)

    def test_worker_parent_eof_requests_exit(self):
        server = SimpleNamespace(should_exit=False)
        with patch.object(managed_worker.sys, "stdin", io.StringIO("")):
            managed_worker.watch_parent(server)
        self.assertTrue(server.should_exit)

    def test_worker_error_does_not_print_private_exception(self):
        with patch.object(managed_worker, "build_app", side_effect=ValueError("private-value")), \
             redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(managed_worker.main(["--service", "private", "--port", "8001"]), 1)
        self.assertNotIn("private-value", output.getvalue() + errors.getvalue())

    def test_unexpected_manager_failure_is_sanitized_and_cleans_owned_processes(self):
        plan = launcher.build_plan(arguments())
        child = fake_child(plan[0])
        with patch.object(launcher, "check_ports"), \
             patch.object(launcher, "start_child", side_effect=[child, RuntimeError("private-path secret")]), \
             patch.object(launcher, "stop_children", return_value=True) as cleanup, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.run_services(plan, threading.Event()), 1)
        self.assertEqual(cleanup.call_args.args[0], [child])
        self.assertIn("管理发生异常", errors.getvalue())
        self.assertNotIn("private-path", errors.getvalue())


def free_ports():
    sockets = [socket.socket() for _ in range(3)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


class LauncherHTTPTests(unittest.TestCase):
    def test_worker_stops_when_parent_input_pipe_closes(self):
        spec = launcher.ServiceSpec("import", "文件导入页", free_ports()[0], "/import")
        child = launcher.start_child(spec)
        child.reader = threading.Thread(target=launcher._read_ready, args=(child,), daemon=True)
        child.reader.start()
        try:
            self.assertTrue(child.ready.wait(timeout=15))
            self.assertIsNone(child.process.poll())
            child.process.stdin.close()
            self.assertEqual(child.process.wait(timeout=8), 0)
        finally:
            self.assertTrue(launcher.stop_children([child]))
        with socket.socket() as probe:
            probe.settimeout(0.3)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", spec.port)), 0)

    def execute_http_case(self, *, include_private=False, invalid_case=False):
        ports = free_ports()
        values = dict(demo_port=ports[0], import_port=ports[1], private_port=ports[2])
        if include_private:
            values["case_file"] = str(PROJECT_ROOT / "examples/careeragent_v1_7_private_case_template.json")
        if invalid_case:
            values["case_file"] = str(PROJECT_ROOT / "not_present_private_case.json")
        plan = launcher.build_plan(arguments(**values))
        stop, results, output, errors = threading.Event(), [], io.StringIO(), io.StringIO()
        opener = build_opener(ProxyHandler({}))
        def run():
            results.append(launcher.run_services(plan, stop))
        with redirect_stdout(output), redirect_stderr(errors):
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 20
                while "均已就绪" not in output.getvalue() and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if invalid_case:
                    thread.join(timeout=10)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(results, [1])
                    self.assertNotIn("均已就绪", output.getvalue())
                    self.assertNotIn("not_present_private_case", output.getvalue() + errors.getvalue())
                else:
                    self.assertIn("均已就绪", output.getvalue(), errors.getvalue())
                    for spec in plan:
                        with opener.open(spec.url, timeout=2) as response:
                            self.assertEqual(response.status, 200)
                    request = Request(f"http://127.0.0.1:{ports[1]}/imports/format-json", data=b"{}",
                                      headers={"Content-Type": "application/json", "X-CareerAgent-Import": "local-preview"})
                    with self.assertRaises(HTTPError) as caught:
                        opener.open(request, timeout=2)
                    self.assertEqual(caught.exception.code, 403)
                    if include_private:
                        request = Request(f"http://127.0.0.1:{ports[2]}/private/case",
                                          headers={"X-CareerAgent-Private": "local-readonly"})
                        with opener.open(request, timeout=2) as response:
                            self.assertIn(b"synthetic_template", response.read())
            finally:
                stop.set()
                thread.join(timeout=15)
            self.assertFalse(thread.is_alive(), "本次启动器必须退出")
        if not invalid_case:
            self.assertEqual(results, [0], errors.getvalue())
        for spec in plan:
            with socket.socket() as probe:
                probe.settimeout(0.3)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", spec.port)), 0)

    def test_default_two_pages_are_reachable_and_stop_together(self):
        self.execute_http_case()

    def test_explicit_synthetic_case_starts_three_isolated_pages(self):
        self.execute_http_case(include_private=True)

    def test_invalid_private_case_rolls_back_other_started_services(self):
        self.execute_http_case(invalid_case=True)


if __name__ == "__main__":
    unittest.main()
