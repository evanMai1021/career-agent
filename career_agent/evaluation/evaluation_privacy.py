"""评估素材与报告的保守隐私格式检查；只返回风险类别。"""

import re


SENSITIVE_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(
        r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
    ),
    "local_path": re.compile(
        r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>]+"
        r"|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_.-]+"
        r"|(?<![A-Za-z0-9:/])/(?!/)[^/\s\"'<>]+/"
        r"[^\s\"'<>]+"
    ),
    # Python 的 \b 把中文也视为词字符；这里用 ASCII 边界识别紧邻中文的令牌。
    "credential": re.compile(
        r"(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9_-]{20,}"
        r"|gh[pousr]_[A-Za-z0-9_]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|AKIA[A-Z0-9]{16}"
        r"|Bearer\s+[A-Za-z0-9._~+/-]{20,})(?![A-Za-z0-9_])"
    )
}


def find_sensitive_kinds(payload):
    """递归检查 JSON 式数据；不返回匹配值或所在字段内容。"""
    found = set()
    seen_containers = set()
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            for kind, pattern in SENSITIVE_PATTERNS.items():
                if pattern.search(value):
                    found.add(kind)
        elif isinstance(value, (dict, list, tuple, set)):
            if id(value) in seen_containers:
                continue
            seen_containers.add(id(value))
            if isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            else:
                pending.extend(value)
    return sorted(found)


def privacy_error_message(label, payload):
    """返回不含原值的安全错误；没有命中则返回 None。"""
    kinds = find_sensitive_kinds(payload)
    if not kinds:
        return None
    return f"{label}包含可能的敏感信息（类别：{', '.join(kinds)}）。"
