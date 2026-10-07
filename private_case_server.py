"""独立启动的本机私有案例页面；没有默认资料文件或全局私有应用。"""

from copy import deepcopy
import hashlib
import ipaddress
import json
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from private_case_runner import (
    PrivateCaseError, SafeArgumentParser, analyse_private_case,
    load_private_case, validate_private_case,
)


PRIVATE_PAGE_FILE = Path(__file__).resolve().parent / "private_demo.html"
PRIVATE_REQUEST_HEADER = "local-readonly"
PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
}


class PrivateAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")


def create_private_app(case, *, port=8001):
    """资料只由本机启动调用者注入，启动后使用同一份内存快照。"""
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise PrivateCaseError("端口无效。")
    snapshot = deepcopy(case)
    validate_private_case(snapshot)
    snapshot_id = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    origin = f"http://127.0.0.1:{port}"
    app = FastAPI(title="CareerAgent Private Local Viewer", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        try:
            local_client = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local_client = False
        blocked = (
            not local_client or request.headers.get("host") != f"127.0.0.1:{port}"
            or request.headers.get("origin", origin) != origin
            or request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}
            or any(header in request.headers for header in ("forwarded", "x-forwarded-for", "x-forwarded-host"))
        )
        if blocked:
            response = JSONResponse({"detail": "仅接受本机同源访问。"}, status_code=403)
        elif request.query_params:
            response = JSONResponse({"detail": "不接受查询参数。"}, status_code=422)
        elif request.url.path in {"/private/case", "/private/analyses"} and request.headers.get("x-careeragent-private") != PRIVATE_REQUEST_HEADER:
            response = JSONResponse({"detail": "私有资料请求不符合约定。"}, status_code=403)
        else:
            response = await call_next(request)
        response.headers.update(PRIVATE_HEADERS)
        return response

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        return JSONResponse({"detail": "请求参数无效。"}, status_code=422)

    @app.get("/private", response_class=HTMLResponse)
    def read_page():
        try:
            return HTMLResponse(PRIVATE_PAGE_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            raise HTTPException(status_code=503, detail="私有页面暂不可用。") from None

    @app.get("/private/case")
    def read_case():
        return {"snapshot_id": snapshot_id, "case": deepcopy(snapshot)}

    @app.post("/private/analyses")
    def analyse(payload: PrivateAnalysisRequest):
        if payload.snapshot_id != snapshot_id:
            raise HTTPException(status_code=409, detail="资料快照已变化，请重新加载。")
        try:
            report = analyse_private_case(snapshot)
        except PrivateCaseError:
            raise HTTPException(status_code=503, detail="私有分析暂不可用。") from None
        return {"snapshot_id": snapshot_id, "report": report}

    return app


def main(argv=None):
    parser = SafeArgumentParser(description="只监听 127.0.0.1 的私有资料页面；不会自动加载资料。")
    parser.add_argument("--case-file", required=True, help="明确指定本机手工脱敏 JSON。")
    parser.add_argument("--port", type=int, default=8001, help="本机端口，默认 8001。")
    try:
        args = parser.parse_args(argv)
        app = create_private_app(load_private_case(args.case_file), port=args.port)
    except PrivateCaseError as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 2
    print(f"本机私有资料页面：http://127.0.0.1:{args.port}/private；按 Ctrl+C 停止。")
    print("仅本机脱敏使用；没有身份验证，同机其他进程仍可访问。修改资料后须重启服务。")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, proxy_headers=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
