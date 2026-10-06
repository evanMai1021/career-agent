"""V1.6 固定模拟案例：公开输入、独立预设与真实规则计算结果。"""

from copy import deepcopy

from job_data import validate_candidate_evidence, validate_job
from job_matching import match_job_requirements
from job_analysis_agent import build_trusted_facts


_JOB = {
    "job_id": "demo_csv_assistant",
    "title": "Python 数据处理实习生（模拟岗位）",
    "requirements": [{
        "requirement_id": "req_python_csv",
        "skill_id": "python",
        "description": "使用 Python 完成 CSV 数据清洗，并为清洗逻辑编写测试。",
        "category": "required",
        "priority": 1,
    }],
}
_EVIDENCE = {
    "evidence_id": "ev_csv_script",
    "skill_id": "python",
    "description": "模拟候选人提交了 CSV 清洗脚本与对应测试记录。",
    "level": "project",
    "source": "人工构造的演示材料；并非真实候选人记录。",
    "verified": True,
}
_DEFINITIONS = [
    ("verified_project", "已验证项目证据", "project", True, "matched"),
    ("verified_practice", "已验证练习证据", "practice", True, "partial"),
    ("unverified_claim", "描述尚未核实", "project", False, "unverified"),
    ("no_evidence", "尚无相关证据", None, None, "missing"),
    ("invalid_evidence", "非法验证标记", "project", "true", None),
]
_REASONS = {
    "matched": "技能 ID 相同，且存在已验证的项目或生产级证据，按现有规则进入已匹配。",
    "partial": "技能 ID 相同，但已验证证据仅达到学习或练习层级，按现有规则进入部分匹配。",
    "unverified": "存在相同技能 ID 的描述，但没有已验证证据，因此仍需核实。",
    "missing": "候选人输入中没有相同技能 ID 的证据；分析完成，但该要求缺少支持。",
}


def _make_cases():
    cases = {}
    for case_id, label, level, verified, state in _DEFINITIONS:
        evidence = []
        if level is not None:
            item = deepcopy(_EVIDENCE)
            item.update(level=level, verified=verified)
            if level == "practice":
                item["description"] = "模拟候选人完成了 CSV 清洗练习及练习测试。"
            evidence.append(item)
        # 预设仅由固定案例定义构造，不调用匹配或可信事实生产函数。
        related_ids = ["ev_csv_script"] if evidence else []
        expected_matches = [{
            **deepcopy(_JOB["requirements"][0]),
            "status": state,
            "related_evidence_ids": related_ids,
        }] if state else []
        expected_facts = [{
            "requirement_id": "req_python_csv",
            "skill_id": "python",
            "status": state,
            "related_evidence_ids": related_ids,
            "verified_evidence_ids": related_ids if verified is True else [],
            "unverified_evidence_ids": related_ids if verified is False else [],
            "origin": "python_deterministic_match",
        }] if state else []
        cases[case_id] = {
            "case_id": case_id,
            "label": label,
            "data_kind": "synthetic_demo",
            "job": deepcopy(_JOB),
            "candidate": {"username": "demo_candidate", "evidence": evidence},
            "expected": {
                "execution_status": "completed" if state else "rejected",
                "states": [{"requirement_id": "req_python_csv", "status": state}]
                if state else [],
                "matches": expected_matches,
                "trusted_facts": expected_facts,
            },
        }
    return cases


_CASES = _make_cases()


def list_demo_cases():
    """返回白名单中的模拟输入，不暴露或修改项目历史数据。"""
    return deepcopy(list(_CASES.values()))


def run_demo_case(case_id):
    """运行真实校验与匹配；预期状态来自固定定义，不调用生产函数生成。"""
    if case_id not in _CASES:
        raise KeyError("未知演示案例。")
    case = deepcopy(_CASES[case_id])
    job, candidate = case["job"], case["candidate"]
    error = validate_job(job) or validate_candidate_evidence(candidate)
    analysis = None
    decisions = []
    if error:
        execution_status = "rejected"
        actual_states = []
        steps = ["已读取模拟输入", "结构校验拒绝输入", "未执行匹配或生成可信事实"]
    else:
        matches = match_job_requirements(job, candidate)
        facts = build_trusted_facts(matches, candidate["evidence"])
        analysis = {
            "username": candidate["username"],
            "job_id": job["job_id"],
            "title": job["title"],
            "analysis_mode": "offline_deterministic",
            "model_generated": False,
            "matches": matches,
            "trusted_facts": facts,
        }
        actual_states = [{"requirement_id": match["requirement_id"],
                          "status": match["status"]} for match in matches]
        decisions = [{"requirement_id": match["requirement_id"],
                      "reason": _REASONS[match["status"]]} for match in matches]
        execution_status = "completed"
        steps = ["已读取模拟输入", "结构校验通过", "已执行四态匹配", "已生成可信事实"]
    return {
        "case": case,
        "execution_status": execution_status,
        "error": error,
        "steps": steps,
        "analysis": analysis,
        "decisions": decisions,
        "verification": {
            "passed": execution_status == case["expected"]["execution_status"]
            and actual_states == case["expected"]["states"]
            and (analysis["matches"] if analysis else []) == case["expected"]["matches"]
            and (analysis["trusted_facts"] if analysis else []) == case["expected"]["trusted_facts"],
            "actual_states": actual_states,
        },
    }
