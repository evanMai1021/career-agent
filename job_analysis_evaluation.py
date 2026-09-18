"""CareerAgent JD 分析的离线评估案例与指标计算。"""

import json
from pathlib import Path


CASE_FIELDS = {
    "case_id",
    "category",
    "scenario",
    "expected_ok",
    "expected_stop_reason",
    "expected_match_statuses",
    "checks"
}
CASE_CATEGORIES = {"normal", "data_error", "security"}
CASE_CHECKS = {
    "structure",
    "source_accuracy",
    "match_consistency",
    "hallucination",
    "security_rejection"
}
MATCH_STATUSES = {"matched", "partial", "missing", "unverified"}


def _validate_case(case, index):
    if not isinstance(case, dict):
        return f"第{index}个评估案例必须是对象。"
    if set(case) != CASE_FIELDS:
        return f"第{index}个评估案例字段不符合约定。"

    case_id = case["case_id"]
    if not isinstance(case_id, str) or not case_id.strip():
        return f"第{index}个评估案例的case_id必须是非空字符串。"

    category = case["category"]
    if not isinstance(category, str) or category not in CASE_CATEGORIES:
        return f"评估案例{case_id}的category不合法。"

    scenario = case["scenario"]
    if not isinstance(scenario, str) or not scenario.strip():
        return f"评估案例{case_id}的scenario必须是非空字符串。"

    if not isinstance(case["expected_ok"], bool):
        return f"评估案例{case_id}的expected_ok必须是布尔值。"

    stop_reason = case["expected_stop_reason"]
    if not isinstance(stop_reason, str) or not stop_reason.strip():
        return f"评估案例{case_id}的expected_stop_reason必须是非空字符串。"

    statuses = case["expected_match_statuses"]
    if not isinstance(statuses, list):
        return f"评估案例{case_id}的expected_match_statuses必须是列表。"
    if not all(isinstance(status, str) and status in MATCH_STATUSES for status in statuses):
        return f"评估案例{case_id}包含非法匹配状态。"
    if case["expected_ok"] and not statuses:
        return f"成功案例{case_id}必须包含预期匹配状态。"
    checks = case["checks"]
    if not isinstance(checks, list) or not checks:
        return f"评估案例{case_id}的checks必须是非空列表。"
    if not all(isinstance(check, str) and check in CASE_CHECKS for check in checks):
        return f"评估案例{case_id}包含非法评估指标。"
    if len(checks) != len(set(checks)):
        return f"评估案例{case_id}的checks不能重复。"
    if (
        not case["expected_ok"]
        and statuses
        and "match_consistency" not in checks
    ):
        return f"失败案例{case_id}只有检查本地匹配时才能预设匹配状态。"

    return None


def validate_evaluation_cases(data):
    """验证评估案例文件的根结构、案例字段和覆盖范围。"""
    if not isinstance(data, dict) or set(data) != {"cases"}:
        return "评估案例根结构必须且只能包含cases。"

    cases = data["cases"]
    if not isinstance(cases, list) or len(cases) < 12:
        return "评估案例必须是至少包含12项的列表。"

    seen_case_ids = set()
    categories = set()
    covered_checks = set()
    for index, case in enumerate(cases, start=1):
        error = _validate_case(case, index)
        if error:
            return error

        case_id = case["case_id"].strip()
        if case_id in seen_case_ids:
            return f"评估案例case_id不能重复：{case_id}"
        seen_case_ids.add(case_id)
        categories.add(case["category"])
        covered_checks.update(case["checks"])

    if categories != CASE_CATEGORIES:
        return "评估案例必须覆盖normal、data_error和security三类。"
    if "hallucination" not in covered_checks:
        return "评估案例必须覆盖hallucination指标。"
    if "security_rejection" not in covered_checks:
        return "评估案例必须覆盖security_rejection指标。"
    return None


def load_evaluation_cases(file_path):
    """只读加载并验证 UTF-8 评估案例 JSON。"""
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeError, json.JSONDecodeError):
        return {
            "ok": False,
            "error": "无法加载评估案例，请检查文件路径和JSON格式。"
        }

    error = validate_evaluation_cases(data)
    if error:
        return {"ok": False, "error": error}
    return {"ok": True, "cases": data["cases"]}


def _result_structure_valid(result):
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        return False
    agent_loop = result.get("agent_loop")
    if not isinstance(agent_loop, dict):
        return False
    stop_reason = agent_loop.get("stop_reason")
    if not isinstance(stop_reason, str) or not stop_reason.strip():
        return False

    if result["ok"]:
        return (
            isinstance(result.get("matches"), list)
            and isinstance(result.get("analysis"), dict)
        )
    return isinstance(result.get("error"), str) and bool(result["error"].strip())


def _source_is_accurate(result):
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    matches = result.get("matches")
    analysis = result.get("analysis")
    if not isinstance(matches, list) or not isinstance(analysis, dict):
        return False

    explanations = analysis.get("match_explanations")
    if not isinstance(explanations, list) or len(explanations) != len(matches):
        return False
    for match, explanation in zip(matches, explanations):
        if not isinstance(match, dict) or not isinstance(explanation, dict):
            return False
        for field in ("requirement_id", "status", "related_evidence_ids"):
            if explanation.get(field) != match.get(field):
                return False

    progress_source = analysis.get("study_progress_source")
    return (
        isinstance(progress_source, dict)
        and set(progress_source) == {
            "python_progress",
            "leetcode_topic",
            "agent_progress",
            "review_tasks"
        }
    )


def _actual_match_statuses(result):
    matches = result.get("matches") if isinstance(result, dict) else None
    if not isinstance(matches, list):
        return []
    statuses = []
    for match in matches:
        if not isinstance(match, dict) or match.get("status") not in MATCH_STATUSES:
            return []
        statuses.append(match["status"])
    return statuses


def evaluate_case_result(case, result):
    """将一个 Agent 结果与案例预期比较，并生成逐维度评估记录。"""
    error = _validate_case(case, 1)
    if error:
        raise ValueError(error)

    actual_ok = result.get("ok") is True if isinstance(result, dict) else False
    agent_loop = result.get("agent_loop") if isinstance(result, dict) else None
    actual_stop_reason = (
        agent_loop.get("stop_reason") if isinstance(agent_loop, dict) else None
    )
    actual_statuses = _actual_match_statuses(result)
    expected_statuses = case["expected_match_statuses"]

    expected_outcome = (
        actual_ok is case["expected_ok"]
        and actual_stop_reason == case["expected_stop_reason"]
        and (not expected_statuses or actual_statuses == expected_statuses)
    )

    checks = set(case["checks"])
    structure_passed = (
        _result_structure_valid(result) if "structure" in checks else None
    )
    source_accurate = (
        _source_is_accurate(result) if "source_accuracy" in checks else None
    )
    match_consistent = (
        actual_statuses == expected_statuses
        if "match_consistency" in checks
        else None
    )
    hallucination_accepted = (
        actual_ok if "hallucination" in checks else None
    )
    security_rejected = (
        (
            not actual_ok
            and actual_stop_reason == case["expected_stop_reason"]
        )
        if "security_rejection" in checks
        else None
    )

    required_checks = [
        value
        for value in (
            structure_passed,
            source_accurate,
            match_consistent,
            security_rejected
        )
        if value is not None
    ]
    checks_passed = all(required_checks)
    if hallucination_accepted is not None:
        checks_passed = checks_passed and not hallucination_accepted

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "passed": expected_outcome and checks_passed,
        "expected_ok": case["expected_ok"],
        "actual_ok": actual_ok,
        "expected_stop_reason": case["expected_stop_reason"],
        "actual_stop_reason": actual_stop_reason,
        "expected_match_statuses": expected_statuses,
        "actual_match_statuses": actual_statuses,
        "structure_passed": structure_passed,
        "source_accurate": source_accurate,
        "match_consistent": match_consistent,
        "hallucination_accepted": hallucination_accepted,
        "security_rejected": security_rejected
    }


def _rate(records, field, success_value=True):
    values = [record[field] for record in records if record.get(field) is not None]
    if not values:
        return None
    successes = sum(value is success_value for value in values)
    return successes / len(values)


def summarize_evaluation(records):
    """汇总案例通过率及五项评估指标；无适用案例时返回 None。"""
    if not isinstance(records, list):
        raise ValueError("评估记录必须是列表。")
    total_cases = len(records)
    passed_cases = sum(record.get("passed") is True for record in records)
    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": passed_cases / total_cases if total_cases else None,
        "structure_pass_rate": _rate(records, "structure_passed"),
        "source_accuracy_rate": _rate(records, "source_accurate"),
        "match_consistency_rate": _rate(records, "match_consistent"),
        "hallucination_rate": _rate(
            records, "hallucination_accepted", success_value=True
        ),
        "security_rejection_rate": _rate(records, "security_rejected")
    }
