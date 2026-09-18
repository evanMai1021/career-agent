"""使用脱敏临时数据和模型替身实际运行 CareerAgent V1.1 评估集。"""

import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from job_analysis_agent import run_job_analysis_agent
from job_analysis_evaluation import load_evaluation_cases, run_evaluation_suite
from job_matching import (
    get_candidate_evidence,
    get_job_requirements,
    match_job_requirements
)
from main import get_study_progress


FIXTURE_FIELDS = {"fixture_id", "job", "candidate", "progress"}


def load_evaluation_fixtures(file_path):
    """只读加载评估夹具；业务数据是否合法由实际只读工具负责验证。"""
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeError, json.JSONDecodeError):
        return {"ok": False, "error": "无法加载评估夹具。"}

    if not isinstance(data, dict) or set(data) != {"fixtures"}:
        return {"ok": False, "error": "评估夹具根结构必须且只能包含fixtures。"}
    fixtures = data["fixtures"]
    if not isinstance(fixtures, list) or not fixtures:
        return {"ok": False, "error": "评估夹具必须是非空列表。"}

    fixture_map = {}
    for index, fixture in enumerate(fixtures, start=1):
        if not isinstance(fixture, dict) or set(fixture) != FIXTURE_FIELDS:
            return {"ok": False, "error": f"第{index}个评估夹具字段不符合约定。"}
        fixture_id = fixture["fixture_id"]
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            return {"ok": False, "error": f"第{index}个评估夹具ID不能为空。"}
        fixture_id = fixture_id.strip()
        if fixture_id in fixture_map:
            return {"ok": False, "error": f"评估夹具ID不能重复：{fixture_id}"}
        if not all(isinstance(fixture[field], dict) for field in (
            "job", "candidate", "progress"
        )):
            return {"ok": False, "error": f"评估夹具{fixture_id}的数据必须是对象。"}
        fixture_map[fixture_id] = fixture
    return {"ok": True, "fixtures": fixture_map}


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False)
        )
    )


def _response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls or []
        ))],
        usage=SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2
        )
    )


class _ScriptedCompletions:
    def __init__(self, actions):
        self._actions = list(actions)

    def create(self, **_kwargs):
        if not self._actions:
            raise RuntimeError("离线模型替身没有更多响应。")
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class _ScriptedClient:
    def __init__(self, actions):
        self.chat = SimpleNamespace(
            completions=_ScriptedCompletions(actions)
        )


def _valid_analysis(job, candidate, progress):
    matches = match_job_requirements(job, candidate)
    explanations = []
    learning_tasks = []
    questions = []
    for match in matches:
        explanations.append({
            "requirement_id": match["requirement_id"],
            "status": match["status"],
            "related_evidence_ids": copy.deepcopy(
                match["related_evidence_ids"]
            ),
            "summary": "该结论仅依据脱敏岗位要求和对应证据ID生成。"
        })
        if match["status"] != "matched":
            learning_tasks.append({
                "requirement_id": match["requirement_id"],
                "task": "围绕该岗位要求完成一个可验证的本地练习。"
            })
        questions.append({
            "requirement_id": match["requirement_id"],
            "question": "你会如何用真实证据说明这项能力？"
        })
    return {
        "match_explanations": explanations,
        "learning_tasks": learning_tasks,
        "interview_questions": questions,
        "study_progress_source": copy.deepcopy(progress)
    }


def _standard_tool_actions(job_id, username, order, final_analysis):
    calls = {
        "job": _response(tool_calls=[_tool_call(
            "call_job", "get_job_requirements", {"job_id": job_id}
        )]),
        "evidence": _response(tool_calls=[_tool_call(
            "call_evidence", "get_candidate_evidence", {"username": username}
        )]),
        "progress": _response(tool_calls=[_tool_call(
            "call_progress", "get_study_progress", {"username": username}
        )])
    }
    return [calls[name] for name in order] + [
        _response(content=json.dumps(final_analysis, ensure_ascii=False))
    ]


def _client_for_case(case, fixture):
    behavior = case["model_behavior"]
    job_id = fixture["job"].get("job_id", "eval_job")
    username = fixture["candidate"].get("username", "eval_user")
    try:
        analysis = _valid_analysis(
            fixture["job"], fixture["candidate"], fixture["progress"]
        )
    except (KeyError, TypeError, ValueError):
        analysis = {}

    if behavior == "model_error":
        return _ScriptedClient([ConnectionError("offline evaluation")])
    if behavior == "cross_user":
        return _ScriptedClient([_response(tool_calls=[_tool_call(
            "call_cross_user",
            "get_candidate_evidence",
            {"username": "other_user"}
        )])])
    if behavior == "cross_job":
        return _ScriptedClient([_response(tool_calls=[_tool_call(
            "call_cross_job",
            "get_job_requirements",
            {"job_id": "other_job"}
        )])])
    if behavior == "unauthorized_write":
        return _ScriptedClient([_response(tool_calls=[_tool_call(
            "call_write",
            "update_study_progress",
            {"username": username}
        )])])
    if behavior == "unapproved_file_path":
        return _ScriptedClient([_response(tool_calls=[_tool_call(
            "call_path",
            "get_job_requirements",
            {"job_id": job_id, "jobs_file": ".env"}
        )])])

    if behavior == "fabricated_evidence":
        analysis["match_explanations"][0]["related_evidence_ids"] = [
            "ev_not_real"
        ]
    elif behavior == "fabricated_requirement":
        analysis["match_explanations"][0]["requirement_id"] = (
            "req_nonexistent_skill"
        )

    if behavior == "complete_different_order":
        order = ("progress", "evidence", "job")
    elif behavior == "complete_progress_first":
        order = ("progress", "job", "evidence")
    else:
        order = ("job", "evidence", "progress")
    return _ScriptedClient(_standard_tool_actions(
        job_id, username, order, analysis
    ))


def execute_evaluation_case(case, fixtures):
    """在临时目录中使用真实工具函数和离线模型替身执行一个案例。"""
    fixture = fixtures.get(case["fixture_id"])
    if fixture is None:
        raise ValueError(f"评估案例引用了不存在的夹具：{case['fixture_id']}")

    with tempfile.TemporaryDirectory(prefix="careeragent_eval_") as temp_dir:
        temp_path = Path(temp_dir)
        jobs_path = temp_path / "jobs.json"
        evidence_path = temp_path / "candidate_evidence.json"
        progress_path = temp_path / "study_progress.json"
        job = copy.deepcopy(fixture["job"])
        candidate = copy.deepcopy(fixture["candidate"])
        progress = copy.deepcopy(fixture["progress"])
        jobs_path.write_text(
            json.dumps({"jobs": [job]}, ensure_ascii=False),
            encoding="utf-8"
        )
        evidence_path.write_text(
            json.dumps({"candidates": [candidate]}, ensure_ascii=False),
            encoding="utf-8"
        )
        progress_path.write_text(
            json.dumps({candidate.get("username", "eval_user"): progress}, ensure_ascii=False),
            encoding="utf-8"
        )

        job_tool = get_job_requirements
        if case["model_behavior"] == "identity_conflict":
            def conflicting_job_tool(job_id, file_path):
                result = get_job_requirements(job_id, file_path)
                if result.get("ok"):
                    result["job_id"] = "other_job"
                return result
            job_tool = conflicting_job_tool

        result = run_job_analysis_agent(
            username=candidate.get("username", "eval_user"),
            job_id=job.get("job_id", "eval_job"),
            jobs_file=jobs_path,
            evidence_file=evidence_path,
            progress_file=progress_path,
            get_job_tool=job_tool,
            get_evidence_tool=get_candidate_evidence,
            get_progress_tool=get_study_progress,
            client=_client_for_case(case, fixture)
        )

    expected_context = {"study_progress": progress}
    try:
        expected_context["matches"] = match_job_requirements(job, candidate)
    except (KeyError, TypeError, ValueError):
        expected_context["matches"] = []
    return {"result": result, "expected_context": expected_context}


def run_project_evaluation(project_root):
    """加载项目内脱敏案例与夹具并实际运行整个离线评估集。"""
    project_root = Path(project_root)
    loaded_cases = load_evaluation_cases(project_root / "evaluation_cases.json")
    if not loaded_cases["ok"]:
        return loaded_cases
    loaded_fixtures = load_evaluation_fixtures(
        project_root / "evaluation_fixtures.json"
    )
    if not loaded_fixtures["ok"]:
        return loaded_fixtures

    fixture_ids = set(loaded_fixtures["fixtures"])
    missing = sorted({
        case["fixture_id"]
        for case in loaded_cases["cases"]
        if case["fixture_id"] not in fixture_ids
    })
    if missing:
        return {"ok": False, "error": f"缺少评估夹具：{', '.join(missing)}"}

    report = run_evaluation_suite(
        loaded_cases["cases"],
        lambda case: execute_evaluation_case(
            case, loaded_fixtures["fixtures"]
        )
    )
    return {"ok": True, **report}


def main():
    report = run_project_evaluation(Path(__file__).parent)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("ok"):
        return 1
    return 0 if report["summary"]["passed_cases"] == report["summary"]["total_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
