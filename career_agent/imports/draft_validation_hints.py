"""严格校验失败后的有限定位；只输出固定字段路径和原因，不决定草稿是否合法。"""

from career_agent.core.job_data import (
    JOB_FIELDS, REQUIREMENT_FIELDS, CANDIDATE_FIELDS, EVIDENCE_FIELDS,
    ALLOWED_REQUIREMENT_CATEGORIES, ALLOWED_EVIDENCE_LEVELS,
)
from career_agent.services.private_case_runner import ID_PATTERN, QUALIFICATION_FIELDS


def draft_field_errors(draft):
    """最多八项；路径只由约定字段和有上限的数组下标构造，绝不引用输入值或未知键。"""
    issues = []

    def add(path, reason):
        if len(issues) < 8:
            issues.append({"path": path, "reason": reason})

    def shape(value, fields, path):
        if not isinstance(value, dict):
            add(path, "object")
            return False
        if set(value) != set(fields):
            add(path, "fields")
        return True

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def strings(value, fields, prefix):
        for field in fields:
            if not text(value.get(field)):
                add(prefix + field, "text")

    def rows(value, path, limit, *, required=False):
        if not isinstance(value, list) or (required and not value):
            add(path, "list")
            return []
        if len(value) > limit:
            add(path, "limit")
        return value[:limit]

    fields = ("case_id", "data_kind", "notice", "job", "candidate", "qualifications")
    if not shape(draft, fields, "draft"):
        return issues
    strings(draft, ("case_id", "notice"), "")
    if isinstance(draft.get("case_id"), str) and not ID_PATTERN.fullmatch(draft["case_id"]):
        add("case_id", "identifier")
    if draft.get("data_kind") not in ("synthetic_private_test", "real_source_sanitized_draft"):
        add("data_kind", "data_kind")

    for section, section_fields, collection, row_fields, limit in (
        ("job", JOB_FIELDS, "requirements", REQUIREMENT_FIELDS, 40),
        ("candidate", CANDIDATE_FIELDS, "evidence", EVIDENCE_FIELDS, 60),
    ):
        value = draft.get(section)
        if value is None:
            continue  # 缺项 null 仍按原约定由 schema_valid 标记，而非字段错误。
        if not shape(value, section_fields, section):
            continue
        identifier = "job_id" if section == "job" else "username"
        strings(value, (identifier, "title") if section == "job" else (identifier,), section + ".")
        if isinstance(value.get(identifier), str) and not ID_PATTERN.fullmatch(value[identifier]):
            add(section + "." + identifier, "identifier")
        seen = set()
        for index, item in enumerate(rows(value.get(collection), section + "." + collection, limit, required=section == "job")):
            path = f"{section}.{collection}[{index}]"
            if not shape(item, row_fields, path):
                continue
            row_id = "requirement_id" if section == "job" else "evidence_id"
            strings(item, (row_id, "skill_id", "description") if section == "job" else (row_id, "skill_id", "description", "source"), path + ".")
            key = item.get(row_id)
            if isinstance(key, str):
                normalized = key.strip()
                if normalized in seen:
                    add(path + "." + row_id, "duplicate")
                seen.add(normalized)
            if section == "job":
                if not isinstance(item.get("category"), str) or item["category"] not in ALLOWED_REQUIREMENT_CATEGORIES:
                    add(path + ".category", "category")
                if type(item.get("priority")) is not int or item["priority"] not in (1, 2, 3):
                    add(path + ".priority", "priority")
            else:
                if not isinstance(item.get("level"), str) or item["level"] not in ALLOWED_EVIDENCE_LEVELS:
                    add(path + ".level", "level")
                if item.get("verified") is not False:
                    add(path + ".verified", "false_only")

    seen = set()
    for index, item in enumerate(rows(draft.get("qualifications"), "qualifications", 10)):
        path = f"qualifications[{index}]"
        if not shape(item, QUALIFICATION_FIELDS, path):
            continue
        strings(item, sorted(QUALIFICATION_FIELDS), path + ".")
        if item.get("verification") != "unverified":
            add(path + ".verification", "unverified_only")
        key = item.get("qualification_id")
        if isinstance(key, str):
            if key in seen:
                add(path + ".qualification_id", "duplicate")
            seen.add(key)
    return issues
