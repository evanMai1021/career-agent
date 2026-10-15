"""统一启动器的内部工作进程；就绪标记和标准输入退出协议不属于 HTTP 接口。"""

import sys
import threading

import uvicorn

from career_agent.cli.start_services import READY_MARKER
from career_agent.services.private_case_runner import SafeArgumentParser


def build_app(args):
    if args.service == "demo":
        from career_agent.services.api_app import app
        return app
    if args.service == "import":
        from career_agent.services.file_import_server import create_import_app
        return create_import_app(port=args.port, enable_model_format=args.enable_model_format)
    from career_agent.services.private_case_runner import load_private_case
    from career_agent.services.private_case_server import create_private_app
    return create_private_app(load_private_case(args.case_file), port=args.port)


class ReadyServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started:
            print(READY_MARKER, flush=True)


def watch_parent(server):
    try:
        # STOP 或管道 EOF 都请求退出；父进程意外结束不会让服务长期脱离管理。
        sys.stdin.readline(16)
    finally:
        server.should_exit = True


def main(argv=None):
    parser = SafeArgumentParser(description="统一启动器内部工作进程。")
    parser.add_argument("--service", choices=("demo", "import", "private"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--case-file")
    parser.add_argument("--enable-model-format", action="store_true")
    try:
        args = parser.parse_args(argv)
        app = build_app(args)
        server = ReadyServer(uvicorn.Config(app, host="127.0.0.1", port=args.port,
                                          access_log=False, proxy_headers=False, log_level="warning",
                                          timeout_graceful_shutdown=3))
        threading.Thread(target=watch_parent, args=(server,), daemon=True).start()
        server.run()
        return 0
    except Exception:
        # 子进程异常不转发原文、路径或 SDK 错误给统一启动器。
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
