"""有限大小的本机文本提取；不读路径、不写原件、不执行文档内容。"""

import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import warnings
import zipfile

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_SEGMENTS = 2000
MAX_PAGES = 20
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
WORKER_SECONDS = 10
WORKER_MEMORY_BYTES = 512 * 1024 * 1024
FORMATS = {"txt", "pdf", "docx"}
ERRORS = {
    "type": "只接受 PDF、UTF-8 TXT 或 DOCX；旧式 DOC 请先另存为 DOCX。",
    "size": "文件不能为空，且不能超过 2 MiB。",
    "encoding": "TXT 必须是 UTF-8 编码，且不能是二进制文件。",
    "invalid": "文件无法解析，可能损坏、加密或与所选类型不符。",
    "encrypted": "不支持加密或密码保护的文档。",
    "empty": "没有提取到文字；扫描件或纯图片需要另行识别，本页不支持。",
    "limit": "文档页数、解压大小、段落数量或文字量超过本机预览限制。",
    "text": "文本包含异常编码或不允许的控制字符。",
    "timeout": "提取超过 10 秒，已停止本次解析，请换用较小文件。",
    "resource": "解析资源限制不可用或已超限，请重试较小文件。",
}


class FileImportError(ValueError):
    def __init__(self, code):
        self.code = code if code in ERRORS else "invalid"
        super().__init__(ERRORS[self.code])


def validate_input(content, kind):
    if not isinstance(kind, str) or kind not in FORMATS:
        raise FileImportError("type")
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_FILE_BYTES:
        raise FileImportError("size")


def _safe_text(text):
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise FileImportError("text") from None
    for index, ch in enumerate(text):
        number = ord(ch)
        if number == 13 and text[index:index + 2] == "\r\n":
            continue
        if (number < 32 and number not in {9, 10}) or 127 <= number <= 159:
            raise FileImportError("text")
    return text


def _extract(content, kind):
    """只在受限工作进程内调用；测试可直接验证提取规则。"""
    validate_input(content, kind)
    segments = []
    total = 0

    def add(label, text):
        nonlocal total
        _safe_text(text)
        total += len(text)
        if total > MAX_TEXT_CHARS or len(segments) >= MAX_SEGMENTS:
            raise FileImportError("limit")
        segments.append({"location": label, "text": text})

    if kind == "txt":
        if content.startswith((b"%PDF-", b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
            raise FileImportError("encoding")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeError:
            raise FileImportError("encoding") from None
        _safe_text(text)
        for index, line in enumerate(text.splitlines(), 1):
            add(f"第 {index} 行", line)
        notes = ["行号对应解码后的原始文本；空行保留，UTF-8 BOM 不作为正文。"]
    elif kind == "pdf":
        from pypdf import PdfReader
        if not content.startswith(b"%PDF-"):
            raise FileImportError("invalid")
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise FileImportError("encrypted")
        if len(reader.pages) > MAX_PAGES:
            raise FileImportError("limit")
        for index, page in enumerate(reader.pages, 1):
            add(f"第 {index} 页", page.extract_text() or "")
        notes = ["保留全部页的位置，包括空白页；无文字不等于原页没有内容。",
                 "文字顺序和排版可能不准确，图片不识别；须与原件人工对照。"]
    else:
        from docx import Document
        from docx.text.paragraph import Paragraph
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            items = archive.infolist()
            names = [item.filename for item in items]
            if (len(items) > 256 or len(names) != len(set(names))
                    or sum(item.file_size for item in items) > MAX_ARCHIVE_BYTES
                    or any(item.flag_bits & 1 for item in items)
                    or any(item.file_size > max(1, item.compress_size) * 200 for item in items)):
                raise FileImportError("limit")
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise FileImportError("invalid")
            if any("vbaproject" in name.lower() or name.startswith("word/embeddings/") for name in names):
                raise FileImportError("invalid")
        document = Document(io.BytesIO(content))

        def blocks(parent, prefix, depth=0):
            if depth > 8:
                raise FileImportError("limit")
            for index, item in enumerate(parent.iter_inner_content(), 1):
                label = f"{prefix}第 {index} 块"
                if isinstance(item, Paragraph):
                    add(label, item.text)
                else:
                    seen = set()
                    for row_index, row in enumerate(item.rows, 1):
                        for cell_index, cell in enumerate(row.cells, 1):
                            if cell._tc in seen:
                                continue
                            seen.add(cell._tc)
                            blocks(cell, f"{label}·表格第 {row_index} 行第 {cell_index} 格·", depth + 1)

        blocks(document, "正文·")
        notes = ["只提取正文普通段落与表格（合并单元格不重复）；位置是结构顺序，不是 Word 页码。",
                 "图片、文本框、页眉页脚、脚注及修订等内容可能遗漏；请对照原件，不代表完整简历。"]
    if not any(item["text"].strip() for item in segments):
        raise FileImportError("empty")
    return {"format": kind, "segments": segments, "warnings": notes,
            "verification": "unverified", "analysis_performed": False, "saved": False}


def _memory_limit():
    """只限制本次解析子进程；限制失败时拒绝解析，不静默降级。"""
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("user_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                    ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.GetCurrentProcess.argtypes = []
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    job = api.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_memory = WORKER_MEMORY_BYTES
    if not job or not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        if job:
            api.CloseHandle(job)
        raise FileImportError("resource")
    if not api.AssignProcessToJobObject(job, api.GetCurrentProcess()):
        api.CloseHandle(job)
        raise FileImportError("resource")
    return job  # 工作进程退出时由操作系统关闭，不能在提取前释放限制。


def extract_document(content, kind):
    """通过标准输入传字节，不传文件名/路径；每次启动一个有时限的工作进程。"""
    validate_input(content, kind)
    worker = None
    try:
        worker = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", kind],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        output, _ = worker.communicate(content, timeout=WORKER_SECONDS)
        if worker.returncode != 0 or len(output) > MAX_TEXT_CHARS * 12 + 500_000:
            raise FileImportError("resource")
        result = json.loads(output)
        if "error" in result:
            raise FileImportError(result["error"])
        return result
    except subprocess.TimeoutExpired:
        raise FileImportError("timeout") from None
    except FileImportError:
        raise
    except (OSError, ValueError):
        raise FileImportError("resource") from None
    finally:
        if worker is not None:
            if worker.poll() is None:
                worker.kill()  # 仅本函数创建的工作进程，不查找或终止其他服务。
            worker.communicate()


def _worker_main():
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    try:
        try:
            _job_handle = _memory_limit()
        except Exception:
            raise FileImportError("resource") from None
        content = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        result = _extract(content, sys.argv[2])
    except FileImportError as error:
        result = {"error": error.code}
    except MemoryError:
        result = {"error": "resource"}
    except Exception:
        result = {"error": "invalid"}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker" and sys.argv[2] in FORMATS:
        _worker_main()
    else:
        raise SystemExit(2)
