"""统一管理独立本机服务；不共享草稿、自动寻找私人文件或调用模型。"""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

from career_agent.paths import PROJECT_ROOT
from career_agent.services.private_case_runner import PrivateCaseError, SafeArgumentParser

READY_MARKER = "CAREER_AGENT_SERVICE_READY"
STARTUP_SECONDS = 20
STOP_SECONDS = 6


class LaunchError(ValueError):
    """只携带固定的启动说明，不保存子进程异常或资料。"""


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    label: str
    port: int
    route: str
    case_file: str | None = None
    enable_model_format: bool = False

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}{self.route}"


@dataclass
class OwnedChild:
    spec: ServiceSpec
    process: subprocess.Popen
    ready: threading.Event
    reader: threading.Thread | None = None


def build_plan(args):
    for port in (args.demo_port, args.import_port, args.private_port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise LaunchError("端口须为 1 到 65535 的整数。")
    specs = [ServiceSpec("demo", "演示页", args.demo_port, "/demo"),
             ServiceSpec("import", "文件导入页", args.import_port, "/import",
                         enable_model_format=args.enable_model_format)]
    if args.case_file is not None:
        if not args.case_file.strip():
            raise LaunchError("私有案例路径不能为空。")
        try:
            case_file = str(Path(args.case_file).resolve())
        except (OSError, ValueError):
            raise LaunchError("私有案例路径无效，请检查后重试。") from None
        specs.append(ServiceSpec("private", "私有资料页", args.private_port, "/private", case_file))
    if len({spec.port for spec in specs}) != len(specs):
        raise LaunchError("已启用服务的端口不能重复。")
    return specs


def check_ports(specs):
    """预检查只绑定本机地址，不连接、接管或关闭既有服务。"""
    for spec in specs:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if os.name == "nt":
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind(("127.0.0.1", spec.port))
        except OSError:
            raise LaunchError(f"{spec.label}端口 {spec.port} 不可用，请换端口；未关闭已有服务。") from None


def child_command(spec):
    command = [sys.executable, "-X", "utf8", "-m", "career_agent.services.managed_worker",
               "--service", spec.key, "--port", str(spec.port)]
    if spec.case_file is not None:
        command.extend(["--case-file", spec.case_file])
    if spec.enable_model_format:
        command.append("--enable-model-format")
    return command


def _read_ready(child):
    try:
        # 只有受管理的子进程完成应用启动和端口绑定后才发出该标记。
        while line := child.process.stdout.readline(256):
            if line.rstrip("\r\n") == READY_MARKER:
                child.ready.set()
                return
    except (OSError, ValueError):
        pass


def start_child(spec):
    process = subprocess.Popen(
        child_command(spec), cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return OwnedChild(spec, process, threading.Event())


def stop_children(children):
    """仅向本次保留的 Popen 对象请求退出；不按端口、名称或 PID 扫描终止。"""
    stopped = True
    for child in children:
        if child.process.poll() is None:
            try:
                child.process.stdin.write("STOP\n")
                child.process.stdin.flush()
                child.process.stdin.close()
            except (OSError, ValueError):
                pass
    deadline = time.monotonic() + STOP_SECONDS
    for child in reversed(children):
        process = child.process
        try:
            process.wait(timeout=max(0.05, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    stopped = False
            except OSError:
                stopped = process.poll() is not None and stopped
        except OSError:
            stopped = process.poll() is not None and stopped
        if process.poll() is not None:
            if child.reader is not None:
                child.reader.join(timeout=0.2)
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        else:
            stopped = False
    return stopped


def run_services(specs, stop_event, *, startup_seconds=STARTUP_SECONDS):
    children = []
    exit_code = 0
    try:
        check_ports(specs)
        deadline = time.monotonic() + startup_seconds
        for spec in specs:
            if stop_event.is_set():
                break
            try:
                child = start_child(spec)
            except OSError:
                raise LaunchError(f"{spec.label}进程无法启动，请检查本机环境。") from None
            children.append(child)
            child.reader = threading.Thread(target=_read_ready, args=(child,), daemon=True)
            child.reader.start()
        while len(children) == len(specs) and not stop_event.is_set():
            failed = next((child for child in children if child.process.poll() is not None), None)
            if failed:
                raise LaunchError(f"{failed.spec.label}启动失败，请检查资料、端口或本机环境。")
            if all(child.ready.is_set() for child in children):
                break
            if time.monotonic() >= deadline:
                raise LaunchError("启动等待超时，未将服务显示为就绪。")
            stop_event.wait(0.05)
        if len(children) == len(specs) and not stop_event.is_set():
            print("本次服务均已就绪；保持终端开启，按 Ctrl+C 一起停止。", flush=True)
            for spec in specs:
                print(f"{spec.label}：{spec.url}", flush=True)
            while not stop_event.wait(0.1):
                failed = next((child for child in children if child.process.poll() is not None), None)
                if failed:
                    raise LaunchError(f"{failed.spec.label}已退出，正在停止本次其他服务；请处理后重新启动。")
    except LaunchError as error:
        print(f"统一启动未完成：{error}", file=sys.stderr, flush=True)
        exit_code = 1
    except KeyboardInterrupt:
        pass
    except Exception:
        print("服务管理发生异常，正在回收本次进程；请检查本机环境后重试。", file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        if not stop_children(children):
            print("无法确认部分本次服务已退出，请检查本次运行；不要结束其他服务。", file=sys.stderr, flush=True)
            exit_code = 1
        elif children:
            print("本次启动的服务已停止，未关闭其他已有服务。", flush=True)
    return exit_code


@contextmanager
def shutdown_signals(stop_event):
    previous = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop_event.set())
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = SafeArgumentParser(description="一次启动独立本机服务；不共享资料或自动调用模型。")
    parser.add_argument("--demo-port", type=int, default=8000)
    parser.add_argument("--import-port", type=int, default=8002)
    parser.add_argument("--private-port", type=int, default=8001)
    parser.add_argument("--case-file", help="明确指定私有页使用的脱敏 JSON；不指定则不启动私有页。")
    parser.add_argument("--enable-model-format", action="store_true", help="允许导入页在另行确认外发后整理 JSON，可能收费。")
    try:
        args = parser.parse_args(argv)
        specs = build_plan(args)
    except (PrivateCaseError, LaunchError):
        print("启动参数无效；使用 --help 查看端口、私有案例和模型开关。", file=sys.stderr)
        return 2
    print("正在启动独立本机服务，不自动传递资料、调用模型或打开浏览器。", flush=True)
    if args.case_file is None:
        print("私有资料页：未配置，未启动。需要时用 --case-file 明确指定脱敏 JSON。", flush=True)
    print("仅用于本机虚构／脱敏资料，无身份验证，不用于共享电脑、公网、代理或端口转发。", flush=True)
    print("模型整理：" + ("已允许；仍须在导入页明确同意外发，可能产生费用。" if args.enable_model_format else "关闭；不需要密钥。"), flush=True)
    stop_event = threading.Event()
    with shutdown_signals(stop_event):
        return run_services(specs, stop_event)


if __name__ == "__main__":
    raise SystemExit(main())
