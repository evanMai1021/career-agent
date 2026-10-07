"""独立的本机文件文字预览服务；不接入案例分析或保存接口。"""

import asyncio
import ipaddress
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
import uvicorn

from file_importer import ERRORS, FORMATS, MAX_FILE_BYTES, FileImportError, extract_document
from private_case_runner import PrivateCaseError, SafeArgumentParser
from private_case_server import PRIVATE_HEADERS
from text_json_formatter import (
    FormatError, MAX_FORMAT_BODY, format_corrected_text, read_json, validate_draft,
)

PAGE_FILE = Path(__file__).resolve().parent / "file_import.html"
IMPORT_HEADER = "local-preview"
UPLOAD_SECONDS = 15


async def _read_upload(request, limit=MAX_FILE_BYTES):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail=ERRORS["size"] if limit==MAX_FILE_BYTES else "JSON 请求超过格式化大小限制。")
        body.extend(chunk)
    return bytes(body)


def create_import_app(*, port=8002, enable_model_format=False):
    if type(port) is not int or not 1 <= port <= 65535:
        raise PrivateCaseError("端口无效。")
    if type(enable_model_format) is not bool:
        raise PrivateCaseError("模型格式化开关无效。")
    app = FastAPI(title="CareerAgent Local Text Import", docs_url=None, redoc_url=None, openapi_url=None)
    busy = asyncio.Lock()

    @app.middleware("http")
    async def local_boundary(request, call_next):
        try:
            local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        origin = f"http://127.0.0.1:{port}"
        if (not local or request.headers.get("host") != f"127.0.0.1:{port}"
                or request.headers.get("origin", origin) != origin
                or request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}
                or any(name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host"))):
            response = JSONResponse({"detail": "仅接受本机同源访问。"}, status_code=403)
        elif request.query_params:
            response = JSONResponse({"detail": "不接受查询参数。"}, status_code=422)
        elif request.url.path in {"/imports/text", "/imports/format-json", "/imports/validate-json"} and request.headers.get("x-careeragent-import") != IMPORT_HEADER:
            response = JSONResponse({"detail": "导入请求不符合约定。"}, status_code=403)
        else:
            response = await call_next(request)
        response.headers.update(PRIVATE_HEADERS)
        return response

    @app.get("/import", response_class=HTMLResponse)
    def page():
        try:
            page_text = PAGE_FILE.read_text(encoding="utf-8")
            if enable_model_format:
                page_text = page_text.replace("const MODEL_ENABLED=false;", "const MODEL_ENABLED=true;")
            return HTMLResponse(page_text)
        except (OSError, UnicodeError):
            raise HTTPException(status_code=503, detail="导入页面暂不可用。") from None

    @app.post("/imports/text")
    async def import_text(request: Request):
        kind = request.headers.get("x-file-format", "")
        if kind not in FORMATS or request.headers.get("content-type") != "application/octet-stream":
            raise HTTPException(status_code=415, detail=ERRORS["type"])
        length = request.headers.get("content-length")
        if length is not None:
            if not length.isascii() or not length.isdecimal():
                raise HTTPException(status_code=422, detail="请求参数无效。")
            if len(length) > 10 or int(length) > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail=ERRORS["size"])
        if busy.locked():
            raise HTTPException(status_code=503, detail="已有导入正在处理，请稍后重试。")
        async with busy:
            try:
                content = await asyncio.wait_for(_read_upload(request), timeout=UPLOAD_SECONDS)
                return await run_in_threadpool(extract_document, content, kind)
            except (TimeoutError, ClientDisconnect):
                raise HTTPException(status_code=408, detail="文件传输未完成，请重新选择后重试。") from None
            except FileImportError as error:
                status = 413 if error.code in {"size", "limit"} else 503 if error.code == "resource" else 422
                if error.code == "timeout":
                    status = 408
                raise HTTPException(status_code=status, detail=str(error)) from None

    async def read_payload(request):
        if request.headers.get("content-type") != "application/json":
            raise HTTPException(status_code=415, detail="仅接受约定的 JSON 请求。")
        try:
            raw = await asyncio.wait_for(_read_upload(request,MAX_FORMAT_BODY),timeout=UPLOAD_SECONDS)
            return read_json(raw.decode("utf-8"),code="input")
        except (TimeoutError,ClientDisconnect):
            raise HTTPException(status_code=408,detail="请求传输未完成，请重试。") from None
        except (UnicodeError,FormatError):
            raise HTTPException(status_code=422,detail="JSON 请求格式无效。") from None

    @app.post("/imports/format-json")
    async def format_json(request: Request):
        if not enable_model_format:
            raise HTTPException(status_code=403,detail="模型格式化未启用；纯文本提取仍可使用。")
        if busy.locked():
            raise HTTPException(status_code=503,detail="已有操作正在处理，请稍后重试。")
        async with busy:
            payload = await read_payload(request)
            try:
                return await run_in_threadpool(format_corrected_text,payload)
            except FormatError as error:
                status = 503 if error.code == "model" else 408 if error.code == "timeout" else 422
                raise HTTPException(status_code=status,detail=str(error)) from None

    @app.post("/imports/validate-json")
    async def validate_json(request: Request):
        payload = await read_payload(request)
        try:
            if not isinstance(payload,dict) or set(payload) != {"draft"}:
                raise FormatError("json")
            return validate_draft(payload["draft"])
        except FormatError as error:
            raise HTTPException(status_code=422,detail=str(error)) from None

    return app


def main(argv=None):
    parser = SafeArgumentParser(description="本机文件文字导入预览；无默认文件，无保存和分析接口。")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--enable-model-format",action="store_true",help="允许确认后将脱敏校对文字发送到已有千问服务（产生API用量）。")
    try:
        args = parser.parse_args(argv)
        app = create_import_app(port=args.port,enable_model_format=args.enable_model_format)
    except PrivateCaseError:
        print("启动失败：参数无效，使用 --help 查看用法。", file=sys.stderr)
        return 2
    print(f"本机文件导入：http://127.0.0.1:{args.port}/import；按 Ctrl+C 停止。")
    print("先用虚构或脱敏文件；无身份验证，不用于共享电脑、公网或代理。只预览，不保存或分析。")
    if args.enable_model_format:
        print("已启用可选千问 JSON 整理；仅点击并同意外发后发送校对文字，可能产生费用，结果待复核。")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, proxy_headers=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
