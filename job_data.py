"""CareerAgent V0.9a 的岗位与个人证据数据契约。

本模块只负责验证脱敏数据结构，不负责计算岗位匹配，也不调用大模型。
验证函数返回 ``None`` 表示通过，返回字符串表示具体错误原因。
"""


JOB_FIELDS = ["job_id", "title", "requirements"]
REQUIREMENT_FIELDS = [
    "requirement_id",
    "skill_id",
    "description",
    "category",
    "priority"
]
CANDIDATE_FIELDS = ["username", "evidence"]
EVIDENCE_FIELDS = [
    "evidence_id",
    "skill_id",
    "description",
    "level",
    "source",
    "verified"
]

ALLOWED_REQUIREMENT_CATEGORIES = {"required", "preferred"}
ALLOWED_EVIDENCE_LEVELS = {"learning", "practice", "project", "production"}


def _validate_exact_fields(data, expected_fields, label):
    """确保对象没有缺少字段，也没有混入未约定字段。"""
    if not isinstance(data, dict):
        return f"{label}必须是对象。"

    if set(data) != set(expected_fields):
        return f"{label}必须且只能包含字段：{'、'.join(expected_fields)}。"

    return None


def _validate_nonempty_string(value, field_path):
    """字符串类型正确但只有空格时，同样视为无效数据。"""
    if not isinstance(value, str) or not value.strip():
        return f"{field_path}必须是非空字符串。"
    return None


def validate_job(job):
    """验证一个脱敏岗位及其要求列表。"""
    fields_error = _validate_exact_fields(job, JOB_FIELDS, "岗位")
    if fields_error:
        return fields_error

    for field in ("job_id", "title"):
        value_error = _validate_nonempty_string(job[field], f"岗位字段{field}")
        if value_error:
            return value_error

    requirements = job["requirements"]
    if not isinstance(requirements, list) or not requirements:
        return "岗位字段requirements必须是非空列表。"

    seen_requirement_ids = set()
    for index, requirement in enumerate(requirements, start=1):
        label = f"第{index}项岗位要求"
        fields_error = _validate_exact_fields(
            requirement,
            REQUIREMENT_FIELDS,
            label
        )
        if fields_error:
            return fields_error

        for field in ("requirement_id", "skill_id", "description"):
            value_error = _validate_nonempty_string(
                requirement[field],
                f"{label}字段{field}"
            )
            if value_error:
                return value_error

        requirement_id = requirement["requirement_id"].strip()
        if requirement_id in seen_requirement_ids:
            return f"岗位要求ID不能重复：{requirement_id}"
        seen_requirement_ids.add(requirement_id)

        category = requirement["category"]
        if (
            not isinstance(category, str)
            or category not in ALLOWED_REQUIREMENT_CATEGORIES
        ):
            return f"{label}字段category必须是required或preferred。"

        priority = requirement["priority"]
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority not in {1, 2, 3}
        ):
            return f"{label}字段priority必须是1、2或3。"

    return None


def validate_candidate_evidence(candidate):
    """验证一个脱敏候选人的证据列表。"""
    fields_error = _validate_exact_fields(
        candidate,
        CANDIDATE_FIELDS,
        "候选人证据"
    )
    if fields_error:
        return fields_error

    username_error = _validate_nonempty_string(
        candidate["username"],
        "候选人证据字段username"
    )
    if username_error:
        return username_error

    evidence_items = candidate["evidence"]
    if not isinstance(evidence_items, list):
        return "候选人证据字段evidence必须是列表。"

    seen_evidence_ids = set()
    for index, evidence in enumerate(evidence_items, start=1):
        label = f"第{index}项个人证据"
        fields_error = _validate_exact_fields(evidence, EVIDENCE_FIELDS, label)
        if fields_error:
            return fields_error

        for field in ("evidence_id", "skill_id", "description", "source"):
            value_error = _validate_nonempty_string(
                evidence[field],
                f"{label}字段{field}"
            )
            if value_error:
                return value_error

        evidence_id = evidence["evidence_id"].strip()
        if evidence_id in seen_evidence_ids:
            return f"个人证据ID不能重复：{evidence_id}"
        seen_evidence_ids.add(evidence_id)

        level = evidence["level"]
        if (
            not isinstance(level, str)
            or level not in ALLOWED_EVIDENCE_LEVELS
        ):
            return (
                f"{label}字段level必须是learning、practice、"
                "project或production。"
            )

        if not isinstance(evidence["verified"], bool):
            return f"{label}字段verified必须是布尔值。"

    return None


def validate_jobs_data(data):
    """验证 jobs.json 的根结构和岗位 ID 唯一性。"""
    if not isinstance(data, dict) or set(data) != {"jobs"}:
        return "岗位数据根结构必须且只能包含jobs列表。"
    if not isinstance(data["jobs"], list) or not data["jobs"]:
        return "岗位数据字段jobs必须是非空列表。"

    seen_job_ids = set()
    for index, job in enumerate(data["jobs"], start=1):
        job_error = validate_job(job)
        if job_error:
            return f"第{index}个岗位无效：{job_error}"

        job_id = job["job_id"].strip()
        if job_id in seen_job_ids:
            return f"岗位ID不能重复：{job_id}"
        seen_job_ids.add(job_id)

    return None


def validate_candidate_evidence_data(data):
    """验证 candidate_evidence.json 的根结构和用户名唯一性。"""
    if not isinstance(data, dict) or set(data) != {"candidates"}:
        return "个人证据数据根结构必须且只能包含candidates列表。"
    if not isinstance(data["candidates"], list) or not data["candidates"]:
        return "个人证据字段candidates必须是非空列表。"

    seen_usernames = set()
    for index, candidate in enumerate(data["candidates"], start=1):
        candidate_error = validate_candidate_evidence(candidate)
        if candidate_error:
            return f"第{index}个候选人无效：{candidate_error}"

        username = candidate["username"].strip()
        if username in seen_usernames:
            return f"候选人用户名不能重复：{username}"
        seen_usernames.add(username)

    return None
