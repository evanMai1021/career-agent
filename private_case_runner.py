"""只读运行明确指定的本地脱敏案例，不接入 HTTP、模型或写入工具。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

from evaluation_privacy import find_sensitive_kinds
from job_data import validate_candidate_evidence, validate_job
from job_matching import match_job_requirements
from job_analysis_agent import build_trusted_facts


MAX_CASE_BYTES = 2 * 1024 * 1024
STATES = {"matched", "partial", "missing", "unverified"}
LABELS = {"matched": "已匹配", "partial": "部分匹配", "missing": "缺少证据", "unverified": "待核实"}
REQUIRED_FIELDS = {"case_id", "data_kind", "job", "candidate"}
OPTIONAL_FIELDS = {"notice", "source_metadata", "qualifications", "expected"}
QUALIFICATION_FIELDS = {"qualification_id", "required", "declared", "source", "verification", "note"}
SOURCE_FIELDS = {
    "jd": {"kind", "collected_at", "company", "posting_date", "url", "origin_verified", "interpretation_note"},
    "resume": {"kind", "pages", "file_modified_date", "content_independently_verified", "privacy"},
}
ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
LIMITATIONS = [
    "只核对人工整理的结构化输入，不自动理解任意 JD 或证明现实能力。",
    "匹配不足不表示程序执行失败；案例预设核对不等于招聘通过或准确率。",
    "verified 是输入记录标记，程序不会根据简历或项目代码自动升级。",
    "学历及届别仅展示来源声明，不参与技能四态或自动录用判断。",
    "隐私检查仅覆盖常见格式，不保证完全匿名；结果仍属于本地私有资料。",
]


class PrivateCaseError(ValueError):
    """固定安全错误，不含资料原文或文件路径。"""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse 默认会回显未识别参数；私人路径或内容不应进入错误提示。
        raise PrivateCaseError("命令行参数无效；请明确提供 --case-file，使用 --help 查看参数。")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _validate_text_safety(payload):
    """检查全部文本及字段名，不回显原文，也不自动修改资料。"""
    pending = [payload]
    seen = set()
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise PrivateCaseError("案例包含异常 Unicode 字符，请检查文本编码。") from None
            for index, character in enumerate(value):
                code = ord(character)
                # 保留制表、LF 和完整 CRLF；单独 CR 可覆盖终端当前行。
                if code == 13 and value[index:index + 2] == "\r\n":
                    continue
                if (code < 32 and code not in {9, 10}) or 127 <= code <= 159:
                    raise PrivateCaseError("案例包含不允许的控制字符，请先清理文本。")
        elif isinstance(value, (dict, list, tuple)):
            if id(value) in seen:
                continue
            seen.add(id(value))
            if isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            else:
                pending.extend(value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PrivateCaseError("案例 JSON 包含重复字段。")
        result[key] = value
    return result


def _reject_constant(_):
    raise PrivateCaseError("案例 JSON 包含非法数值。")


def load_private_case(file_path):
    """路径由本机调用者指定，只读 JSON，不搜索目录或自动加载个人资料。"""
    try:
        path = Path(file_path)
        if path.suffix.lower() != ".json":
            raise PrivateCaseError("仅接受手工整理的脱敏 JSON 案例，不直接读取 PDF。")
        with path.open("rb") as stream:
            content = stream.read(MAX_CASE_BYTES + 1)
        if len(content) > MAX_CASE_BYTES:
            raise PrivateCaseError("案例文件超过大小限制。")
        return json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except PrivateCaseError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError, RecursionError):
        raise PrivateCaseError("无法读取案例，请检查文件是否存在、编码与 JSON 格式。") from None


def validate_private_case(case):
    """严格约定返回字段；错误信息不回显输入。"""
    if not isinstance(case, dict) or not REQUIRED_FIELDS <= set(case) <= REQUIRED_FIELDS | OPTIONAL_FIELDS:
        raise PrivateCaseError("案例字段不符合约定。")
    _validate_text_safety(case)
    if not isinstance(case["case_id"], str) or not ID_PATTERN.fullmatch(case["case_id"]):
        raise PrivateCaseError("案例 ID 必须使用约定的匿名标识。")
    if case["data_kind"] not in ("real_source_sanitized_draft", "synthetic_private_test"):
        raise PrivateCaseError("案例来源类型不符合约定。")
    if "notice" in case and not _text(case["notice"]):
        raise PrivateCaseError("案例说明无效。")
    if validate_job(case["job"]) or validate_candidate_evidence(case["candidate"]):
        raise PrivateCaseError("岗位或证据结构无效；请检查字段、类型和验证标记。")
    for identifier in [case["candidate"]["username"], case["job"]["job_id"]]:
        if not ID_PATTERN.fullmatch(identifier):
            raise PrivateCaseError("岗位和候选人须使用约定的匿名标识。")
    metadata = case.get("source_metadata", {})
    if not isinstance(metadata, dict) or not set(metadata) <= set(SOURCE_FIELDS):
        raise PrivateCaseError("来源元数据无效。")
    for kind, values in metadata.items():
        if not isinstance(values, dict) or not set(values) <= SOURCE_FIELDS[kind]:
            raise PrivateCaseError("来源元数据字段不符合约定。")
        for field, value in values.items():
            if field in {"origin_verified", "content_independently_verified"}:
                valid = isinstance(value, bool)
            elif field == "pages":
                valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
            else:
                valid = value is None or _text(value)
            if not valid:
                raise PrivateCaseError("来源元数据类型无效。")
    qualifications = case.get("qualifications", [])
    if not isinstance(qualifications, list):
        raise PrivateCaseError("资格声明必须是列表。")
    seen = set()
    for qualification in qualifications:
        if (not isinstance(qualification, dict) or set(qualification) != QUALIFICATION_FIELDS
                or not all(_text(value) for value in qualification.values())
                or qualification["verification"] != "unverified"
                or qualification["qualification_id"] in seen):
            raise PrivateCaseError("资格声明无效；本入口仅展示待核实声明。")
        seen.add(qualification["qualification_id"])
    if "expected" in case:
        expected = case["expected"]
        if (not isinstance(expected, dict) or not {"execution_status", "states"} <= set(expected) <= {"execution_status", "states", "note"}
                or expected["execution_status"] != "completed" or not isinstance(expected["states"], list)):
            raise PrivateCaseError("案例预设无效。")
        requirement_ids = [item["requirement_id"] for item in case["job"]["requirements"]]
        states = expected["states"]
        if len(states) != len(requirement_ids):
            raise PrivateCaseError("预设必须覆盖全部要求，不能只核对部分结果。")
        for item, requirement_id in zip(states, requirement_ids):
            if (not isinstance(item, dict) or set(item) != {"requirement_id", "status"}
                    or item["requirement_id"] != requirement_id
                    or not isinstance(item["status"], str) or item["status"] not in STATES):
                raise PrivateCaseError("预设要求 ID、顺序或状态无效。")
        if "note" in expected and not _text(expected["note"]):
            raise PrivateCaseError("预设说明无效。")
    if find_sensitive_kinds(case):
        raise PrivateCaseError("案例命中常见敏感信息格式，请先脱敏再运行。")


def _outputs_from_states(case, states):
    """从原始输入和明确给定的状态构造预期，不调用生产匹配或事实函数。"""
    matches, facts = [], []
    for requirement, state in zip(case["job"]["requirements"], states):
        related = [item for item in case["candidate"]["evidence"] if item["skill_id"] == requirement["skill_id"]]
        related_ids = [item["evidence_id"] for item in related]
        matches.append({**requirement, "status": state["status"], "related_evidence_ids": related_ids})
        facts.append({
            "requirement_id": requirement["requirement_id"], "skill_id": requirement["skill_id"],
            "status": state["status"], "related_evidence_ids": related_ids,
            "verified_evidence_ids": [item["evidence_id"] for item in related if item["verified"]],
            "unverified_evidence_ids": [item["evidence_id"] for item in related if not item["verified"]],
            "origin": "python_deterministic_match",
        })
    return matches, facts


def _strictly_equal(left, right):
    """比较完整 JSON 结构，同时区分 bool 与 int、列表与其他类型。"""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_strictly_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_strictly_equal(a, b) for a, b in zip(left, right))
    return left == right


def analyse_private_case(case):
    """校验与计算使用同一份快照；不修改调用者资料。"""
    case = deepcopy(case)
    validate_private_case(case)
    try:
        matches = match_job_requirements(case["job"], case["candidate"])
        facts = build_trusted_facts(matches, case["candidate"]["evidence"])
        states = [{"requirement_id": item["requirement_id"], "status": item["status"]} for item in matches]
        if len(states) != len(case["job"]["requirements"]) or any(item["status"] not in STATES for item in states):
            raise ValueError("incomplete-result")
        if not _strictly_equal((matches, facts), _outputs_from_states(case, states)):
            raise ValueError("inconsistent-result")
        if find_sensitive_kinds({"matches": matches, "facts": facts}):
            raise ValueError("unsafe-result")
    except Exception:
        raise PrivateCaseError("分析执行失败，未生成可展示的完整结果。") from None
    expected = case.get("expected")
    verification = {"applicable": expected is not None, "passed": None, "scope": "not_configured"}
    if expected is not None:
        expected_matches, expected_facts = _outputs_from_states(case, expected["states"])
        verification = {
            "applicable": True,
            "passed": _strictly_equal(states, expected["states"]) and _strictly_equal(matches, expected_matches) and _strictly_equal(facts, expected_facts),
            "scope": "execution_matches_and_trusted_facts",
        }
    return {
        "case": case, "execution_status": "completed", "analysis_mode": "offline_deterministic",
        "model_generated": False, "matches": matches, "trusted_facts": facts,
        "verification": verification, "limitations": list(LIMITATIONS),
    }


def run_private_case_file(file_path):
    return analyse_private_case(load_private_case(file_path))


def format_private_report(report):
    """本机可读报告；资格、相关证据及其他资料分别展示，不计算候选人评分。"""
    case = report["case"]
    lines = ["本机私有资料离线分析", f"案例：{case['case_id']}", f"岗位：{case['job']['title']}",
             "执行：完成；未调用模型，未写入文件。", "匹配统计（不是招聘评分）："]
    for state in ("matched", "partial", "unverified", "missing"):
        lines.append(f"  {LABELS[state]}：{sum(item['status'] == state for item in report['matches'])}")
    verification = report["verification"]
    check = "未核对（未配置人工预设）" if not verification["applicable"] else "通过" if verification["passed"] else "未通过"
    lines.append(f"案例预设核对：{check}；不表示能力验证或招聘通过。")
    if case.get("notice"):
        lines.append(case["notice"])
    if case.get("source_metadata"):
        lines.extend(["来源说明（不等于核实）：", json.dumps(case["source_metadata"], ensure_ascii=False)])
    lines.append("资格声明（不参与技能匹配）：")
    for item in case.get("qualifications", []):
        lines.extend([f"  要求：{item['required']}", f"  声明：{item['declared']}（待核实）", f"  来源：{item['source']}", f"  边界：{item['note']}"])
    if not case.get("qualifications"):
        lines.append("  未提供。")
    lines.append("岗位要求与关联证据：")
    evidence_by_id = {item["evidence_id"]: item for item in case["candidate"]["evidence"]}
    used_ids = set()
    for match, fact in zip(report["matches"], report["trusted_facts"]):
        lines.append(f"  [{LABELS[match['status']]}] {match['requirement_id']}：{match['description']}")
        if not match["related_evidence_ids"]:
            lines.append("    当前输入没有相同技能 ID 的证据，不等于现实中不会。")
        for evidence_id in match["related_evidence_ids"]:
            used_ids.add(evidence_id)
            item = evidence_by_id[evidence_id]
            lines.extend([f"    {evidence_id}（{item['level']}，验证标记={item['verified']}）：{item['description']}", f"    来源：{item['source']}"])
        lines.append(f"    可信事实：{json.dumps(fact, ensure_ascii=False)}")
    lines.append("其他证据（未对应本次岗位要求，不会自动替代所缺技能）：")
    for item in case["candidate"]["evidence"]:
        if item["evidence_id"] not in used_ids:
            lines.extend([f"  {item['evidence_id']} / {item['skill_id']}（{item['level']}，验证标记={item['verified']}）：{item['description']}", f"  来源：{item['source']}"])
    if len(used_ids) == len(evidence_by_id):
        lines.append("  无。")
    lines.extend(["局限：", *[f"  {item}" for item in report["limitations"]]])
    return "\n".join(lines)


def main(argv=None):
    parser = SafeArgumentParser(description="只读运行明确指定的本地脱敏 JSON 案例；不启动 HTTP 服务。")
    parser.add_argument("--case-file", required=True, help="本机脱敏案例 JSON，不接收 PDF 或 URL。")
    parser.add_argument("--json", action="store_true", help="在本机终端输出 JSON；仍为私有资料，不应公开。")
    try:
        args = parser.parse_args(argv)
        report = run_private_case_file(args.case_file)
    except PrivateCaseError as error:
        print(f"执行失败：{error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_private_report(report))
    return 1 if report["verification"]["passed"] is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
