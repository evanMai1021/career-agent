import json
import os
from pathlib import Path

from dotenv import load_dotenv

from job_analysis_agent import run_job_analysis_agent
from job_matching import get_candidate_evidence, get_job_requirements
from qwen_agent import run_qwen_agent_loop, run_qwen_update_proposal


# 用户基础资料只负责身份和求职目标；学习进度由工具单独读取。
REQUIRED_PROFILE_FIELDS = [
    "target_role"
]

# 学习进度工具允许读取和更新的字段。
STUDY_TEXT_FIELDS = ["python_progress", "leetcode_topic", "agent_progress"]
STUDY_PROGRESS_FIELDS = STUDY_TEXT_FIELDS + ["review_tasks"]
REVIEW_TASK_FIELDS = ["problem_id", "title", "topics", "status"]

# 本地目录是题号与真实题名/专题的可信来源，模型不能自行改写。
REVIEW_TASK_CATALOG = {
    560: {
        "title": "和为K的子数组",
        "topics": ["前缀和", "哈希表"]
    },
    283: {
        "title": "移动零",
        "topics": ["双指针", "数组"]
    },
    76: {
        "title": "最小覆盖子串",
        "topics": ["滑动窗口", "哈希表"]
    },
    438: {
        "title": "找到字符串中所有字母异位词",
        "topics": ["滑动窗口", "哈希表"]
    },
    239: {
        "title": "滑动窗口最大值",
        "topics": ["单调队列"]
    }
}


def validate_user_profile(user_profile):
    """验证单个用户资料能否安全地交给建议生成函数使用。"""
    # JSON 中的对象会被 json.load() 转换成 Python 字典。
    if not isinstance(user_profile, dict):
        print("用户资料必须是对象")
        raise SystemExit

    # 每个必要字段都必须存在，并且当前 V0 约定字段值都是字符串。
    for field in REQUIRED_PROFILE_FIELDS:
        if field not in user_profile:
            print(f"用户资料缺少必要字段：{field}")
            raise SystemExit
        if not isinstance(user_profile[field], str):
            print(f"用户资料字段必须是字符串：{field}")
            raise SystemExit
        if not user_profile[field].strip():
            print(f"用户资料字段不能为空：{field}")
            raise SystemExit


def generate_advice(study_progress):
    """根据学习进度工具返回的数据，生成三类结构化建议。"""
    # 这三个字段来自 get_study_progress() 的 progress，而不是用户基础资料。
    agent_progress = study_progress["agent_progress"]
    leetcode_topic = study_progress["leetcode_topic"]
    python_progress = study_progress["python_progress"]

    # 先提供三类默认建议，确保即使具体规则未触发，输出结构仍然完整。
    advice = {
        "agent": {
            "task": "继续推进CareerAgent项目。",
            "reason": "当前资料未触发更具体的Agent项目建议。"
        },
        "leetcode": {
            "task": "继续按照当前算法计划练习。",
            "reason": "当前学习进度未触发更具体的LeetCode建议。"
        },
        "python": {
            "task": "继续按照当前Python计划学习。",
            "reason": "当前学习进度未触发更具体的Python建议。"
        }
    }

    # 每条规则只更新自己负责的建议分类，互相之间不会覆盖。
    if "尚未完成" in agent_progress:
        advice["agent"] = {
            "task": "跑通CareerAgent的JSON输入与结构化建议输出。",
            "reason": (
                "当前资料显示尚未完成第一个可运行版本，"
                "应先形成可以实际运行的最小闭环。"
            )
        }

    if leetcode_topic == "滑动窗口":
        advice["leetcode"] = {
            "task": "继续完成最小覆盖子串。",
            "reason": "当前算法专题为滑动窗口。"
        }

    if "JSON" in python_progress:
        advice["python"] = {
            "task": "闭卷完成一次JSON读取、修改、保存和重新加载。",
            "reason": "当前Python学习进度包含JSON，需要巩固完整数据处理流程。"
        }

    return advice


def load_users(file_path, show_errors=True):
    """从 UTF-8 JSON 文件加载全部用户，并验证最外层结构。"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # json.load() 读取文件，并转换成 Python 对象。
            users = json.load(file)
            # 多用户数据必须是“用户名 -> 用户资料”的字典。
            if not isinstance(users, dict):
                if show_errors:
                    print("用户数据根结构必须是对象")
                return None
    except FileNotFoundError:
        if show_errors:
            print("用户数据文件不存在")
        return None
    except json.JSONDecodeError:
        if show_errors:
            print("用户数据文件格式错误")
        return None

    return users


def validate_review_tasks(review_tasks):
    """验证复习任务结构及题号、题名、专题的真实对应关系。"""
    if not isinstance(review_tasks, list):
        return "用户学习进度字段必须是列表：review_tasks"

    required_fields = set(REVIEW_TASK_FIELDS)
    seen_problem_ids = set()
    for index, task in enumerate(review_tasks, start=1):
        if not isinstance(task, dict):
            return f"第{index}项复习任务必须是对象。"
        if set(task) != required_fields:
            return (
                f"第{index}项复习任务必须且只能包含字段："
                "problem_id、title、topics、status。"
            )

        problem_id = task["problem_id"]
        if not isinstance(problem_id, int) or isinstance(problem_id, bool):
            return f"第{index}项复习任务题号必须是整数：problem_id"
        if problem_id in seen_problem_ids:
            return f"复习任务题号不能重复：{problem_id}"
        seen_problem_ids.add(problem_id)

        expected = REVIEW_TASK_CATALOG.get(problem_id)
        if expected is None:
            return f"第{index}项复习任务题号不在本地目录：{problem_id}"

        title = task["title"]
        if not isinstance(title, str) or not title.strip():
            return f"第{index}项复习任务字段必须是非空字符串：title"
        if title.strip() != expected["title"]:
            return f"题号{problem_id}的题名与本地目录不一致。"

        topics = task["topics"]
        if not isinstance(topics, list) or not topics:
            return f"题号{problem_id}的topics必须是非空列表。"
        if not all(isinstance(topic, str) and topic.strip() for topic in topics):
            return f"题号{problem_id}的topics必须只包含非空字符串。"
        normalized_topics = [topic.strip() for topic in topics]
        if len(normalized_topics) != len(set(normalized_topics)):
            return f"题号{problem_id}的topics不能重复。"
        if set(normalized_topics) != set(expected["topics"]):
            return f"题号{problem_id}的专题与本地目录不一致。"

        status = task["status"]
        if not isinstance(status, str) or not status.strip():
            return f"第{index}项复习任务字段必须是非空字符串：status"

    return None


def normalize_review_tasks(review_tasks):
    """使用本地目录统一题名和专题顺序，并清理状态两端空白。"""
    return [
        {
            "problem_id": task["problem_id"],
            "title": REVIEW_TASK_CATALOG[task["problem_id"]]["title"],
            "topics": REVIEW_TASK_CATALOG[task["problem_id"]]["topics"].copy(),
            "status": task["status"].strip()
        }
        for task in review_tasks
    ]


def validate_study_progress_update(field, new_value):
    """只验证一次学习进度更新的字段和值，不读取或修改文件。"""
    if field not in STUDY_PROGRESS_FIELDS:
        return f"不允许更新学习进度字段：{field}"

    if field in STUDY_TEXT_FIELDS:
        if not isinstance(new_value, str):
            return f"学习进度字段必须是字符串：{field}"
        if not new_value.strip():
            return f"学习进度字段不能为空：{field}"

    if field == "review_tasks":
        return validate_review_tasks(new_value)

    return None


def get_study_progress(username, progress_file):
    """读取指定用户的学习进度，并返回可序列化的结构化结果。"""
    # 工具函数复用现有加载能力，并关闭加载函数的控制台提示。
    # 调用者只需要检查返回字典，不必从打印文本中判断成功或失败。
    all_progress = load_users(progress_file, show_errors=False)
    if all_progress is None:
        return {
            "ok": False,
            "error": "无法加载学习进度数据，请检查文件路径和JSON格式。"
        }

    # 用户名是查询条件；空用户名和不存在的用户名都返回清晰错误。
    if not isinstance(username, str) or not username.strip():
        return {"ok": False, "error": "用户名不能为空。"}

    username = username.strip()
    if username not in all_progress:
        return {"ok": False, "error": f"未找到用户：{username}"}

    user_progress = all_progress[username]
    if not isinstance(user_progress, dict):
        return {"ok": False, "error": "用户学习进度必须是对象。"}

    # 进度工具只验证和返回自己的四个字段，不要求求职目标 target_role。
    for field in STUDY_TEXT_FIELDS:
        if field not in user_progress:
            return {"ok": False, "error": f"用户学习进度缺少必要字段：{field}"}
        if not isinstance(user_progress[field], str):
            return {"ok": False, "error": f"用户学习进度字段必须是字符串：{field}"}
        if not user_progress[field].strip():
            return {"ok": False, "error": f"用户学习进度字段不能为空：{field}"}

    if "review_tasks" not in user_progress:
        return {"ok": False, "error": "用户学习进度缺少必要字段：review_tasks"}
    review_tasks_error = validate_review_tasks(user_progress["review_tasks"])
    if review_tasks_error:
        return {"ok": False, "error": review_tasks_error}

    # 只输出约定字段，避免把文件里的其他数据意外暴露给后续调用者。
    progress = {
        "python_progress": user_progress["python_progress"],
        "leetcode_topic": user_progress["leetcode_topic"],
        "agent_progress": user_progress["agent_progress"],
        "review_tasks": normalize_review_tasks(user_progress["review_tasks"])
    }
    return {
        "ok": True,
        "username": username,
        "progress": progress
    }


def update_study_progress(username, field, new_value, progress_file):
    """更新一个学习进度字段，并将结果保存回本地 JSON 文件。"""
    # 模型提案和真正写入复用同一套验证，避免两处规则逐渐不一致。
    validation_error = validate_study_progress_update(field, new_value)
    if validation_error:
        return {"ok": False, "error": validation_error}

    if field == "review_tasks":
        new_value = normalize_review_tasks(new_value)

    # 先通过只读工具完成文件、用户名和原资料结构验证。
    current_result = get_study_progress(username, progress_file)
    if not current_result["ok"]:
        return current_result

    username = current_result["username"]
    all_progress = load_users(progress_file, show_errors=False)
    all_progress[username][field] = new_value

    # 先写临时文件，再替换原文件，降低写入中断造成JSON损坏的风险。
    progress_path = Path(progress_file)
    temp_path = progress_path.with_name(f"{progress_path.name}.tmp")
    try:
        temp_path.write_text(
            json.dumps(all_progress, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        temp_path.replace(progress_path)
    except OSError:
        return {"ok": False, "error": "无法保存学习进度数据。"}

    # 真正从磁盘重新读取，不能只把内存中的 all_progress 当作保存证据。
    verified_result = get_study_progress(username, progress_file)
    if not verified_result["ok"]:
        return {"ok": False, "error": "写入后重新读取验证失败。"}

    updated_progress = verified_result["progress"]
    if updated_progress[field] != new_value:
        return {"ok": False, "error": "写入后重新读取结果与提案不一致。"}
    return {
        "ok": True,
        "username": username,
        "updated_field": field,
        "progress": updated_progress
    }


def resolve_update_proposal(
    proposal,
    confirmation,
    progress_file,
    update_tool=update_study_progress
):
    """根据用户确认决定取消或执行写入，并记录可审计结果。"""
    if confirmation.strip() != "CONFIRM":
        return {
            "ok": True,
            "status": "cancelled",
            "used_tools": [],
            "stop_reason": "user_cancelled",
            "trace": [
                {
                    "step": 2,
                    "action": "user_confirmation",
                    "status": "rejected"
                }
            ]
        }

    trace = [
        {
            "step": 2,
            "action": "user_confirmation",
            "status": "confirmed"
        }
    ]
    update_result = update_tool(
        proposal["username"],
        proposal["field"],
        proposal["new_value"],
        progress_file
    )
    trace.append({
        "step": 3,
        "action": "update_study_progress",
        "status": "success" if update_result["ok"] else "error"
    })

    if not update_result["ok"]:
        return {
            "ok": False,
            "status": "update_failed",
            "error": update_result["error"],
            "used_tools": ["update_study_progress"],
            "stop_reason": "tool_error",
            "trace": trace
        }

    return {
        "ok": True,
        "status": "completed",
        "used_tools": ["update_study_progress"],
        "stop_reason": "completed",
        "trace": trace,
        "updated_field": update_result["updated_field"],
        "progress": update_result["progress"]
    }


def run_agent_loop(username, progress_file, max_steps=3):
    """在固定步数内执行读取进度和生成建议的规则版受控循环。"""
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        return {"ok": False, "error": "max_steps必须是正整数。"}

    progress = None
    used_tools = []
    trace = []

    for step in range(1, max_steps + 1):
        # 第一步只读取数据。写入工具不会被普通建议流程自动调用。
        if progress is None:
            tool_result = get_study_progress(username, progress_file)
            used_tools.append("get_study_progress")
            trace.append({
                "step": step,
                "action": "get_study_progress",
                "status": "success" if tool_result["ok"] else "error"
            })

            if not tool_result["ok"]:
                return {
                    "ok": False,
                    "error": tool_result["error"],
                    "used_tools": used_tools,
                    "agent_loop": {
                        "mode": "rule_based",
                        "max_steps": max_steps,
                        "stop_reason": "tool_error",
                        "trace": trace
                    }
                }

            progress = tool_result["progress"]
            continue

        # 已取得进度后生成建议并主动结束，不消耗剩余循环次数。
        advice = generate_advice(progress)
        trace.append({
            "step": step,
            "action": "generate_advice",
            "status": "success"
        })
        return {
            "ok": True,
            "used_tools": used_tools,
            "advice": advice,
            "agent_loop": {
                "mode": "rule_based",
                "max_steps": max_steps,
                "stop_reason": "completed",
                "trace": trace
            }
        }

    # 循环次数不足以完成全部步骤时，必须明确停止，不能无限运行。
    return {
        "ok": False,
        "error": "Agent循环达到最大步数，任务未完成。",
        "used_tools": used_tools,
        "agent_loop": {
            "mode": "rule_based",
            "max_steps": max_steps,
            "stop_reason": "max_steps_reached",
            "trace": trace
        }
    }


def main():
    """串联用户选择、受控工具调用和结构化建议输出。"""
    # 默认进入千问模式；设置 CAREER_AGENT_MODE=rule 可切回无费用规则模式。
    load_dotenv()
    agent_mode = os.getenv("CAREER_AGENT_MODE", "llm").strip().lower()
    all_users = load_users("users.json")

    # 加载失败时立即结束，避免继续对 None 做用户查询。
    if all_users is None:
        raise SystemExit

    # strip() 去除输入两端空白，也能把纯空格输入变成空字符串。
    username = input("请输入用户名：").strip()

    if not username:
        print("用户名不能为空")
    elif username not in all_users:
        print(f"未找到用户：{username}")
    else:
        # 从“全部用户字典”中取出当前用户的“单个资料字典”。
        user_profile = all_users[username]
        # 基础资料只验证目标岗位等用户信息，不再直接提供学习进度。
        validate_user_profile(user_profile)

        # advice 是学习建议，job 是岗位分析；update 当前只生成写入提案。
        action = input(
            "请选择操作（advice/job/update，直接回车默认为advice）："
        ).strip().lower()
        action_aliases = {
            "": "advice",
            "建议": "advice",
            "岗位分析": "job",
            "更新": "update"
        }
        action = action_aliases.get(action, action)

        if action not in {"advice", "job", "update"}:
            result = {
                "username": username,
                "target_role": user_profile["target_role"],
                "error": "操作只能是advice、job或update。"
            }
            print(json.dumps(result, ensure_ascii=False, indent=4))
            return

        if action == "job":
            if agent_mode != "llm":
                result = {
                    "username": username,
                    "target_role": user_profile["target_role"],
                    "used_tools": [],
                    "error": "岗位分析目前只支持llm模式。"
                }
                print(json.dumps(result, ensure_ascii=False, indent=4))
                return

            job_id = input("请输入岗位ID：").strip()
            result = run_job_analysis_agent(
                username=username,
                job_id=job_id,
                jobs_file="jobs.json",
                evidence_file="candidate_evidence.json",
                progress_file="study_progress.json",
                get_job_tool=get_job_requirements,
                get_evidence_tool=get_candidate_evidence,
                get_progress_tool=get_study_progress
            )
            print(json.dumps(result, ensure_ascii=False, indent=4))
            return

        if action == "update":
            if agent_mode != "llm":
                result = {
                    "username": username,
                    "target_role": user_profile["target_role"],
                    "used_tools": [],
                    "requested_tools": [],
                    "error": "更新提案目前只支持llm模式。"
                }
                print(json.dumps(result, ensure_ascii=False, indent=4))
                return

            user_request = input("请输入明确的更新要求：")
            proposal_result = run_qwen_update_proposal(
                username=username,
                target_role=user_profile["target_role"],
                user_request=user_request,
                validate_update=validate_study_progress_update
            )
            base_result = {
                "username": username,
                "target_role": user_profile["target_role"],
                "used_tools": proposal_result.get("used_tools", []),
                "requested_tools": proposal_result.get("requested_tools", []),
                "agent_loop": proposal_result.get("agent_loop"),
                "model": proposal_result.get("model"),
                "llm_usage": proposal_result.get("llm_usage")
            }
            if not proposal_result["ok"]:
                base_result["error"] = proposal_result["error"]
                print(json.dumps(base_result, ensure_ascii=False, indent=4))
                return

            # 必须先展示模型提案，再询问用户；不能把确认藏在模型回复中。
            proposal = proposal_result["write_proposal"]
            print("\n更新提案：")
            print(json.dumps(proposal, ensure_ascii=False, indent=4))
            confirmation = input(
                "如确认写入，请输入CONFIRM；其他输入将取消："
            )
            resolution = resolve_update_proposal(
                proposal,
                confirmation,
                "study_progress.json",
                update_tool=update_study_progress
            )

            # 把模型提案、用户确认和工具执行合并成一条完整轨迹。
            result = {
                "username": username,
                "target_role": user_profile["target_role"],
                "requested_tools": proposal_result["requested_tools"],
                "used_tools": resolution["used_tools"],
                "model": proposal_result["model"],
                "llm_usage": proposal_result["llm_usage"],
                "status": resolution["status"],
                "write_proposal": proposal,
                "agent_loop": {
                    "mode": "llm_confirmed_update",
                    "max_steps": 3,
                    "stop_reason": resolution["stop_reason"],
                    "trace": (
                        proposal_result["agent_loop"]["trace"]
                        + resolution["trace"]
                    )
                }
            }
            if resolution["ok"] and resolution["status"] == "completed":
                result["updated_field"] = resolution["updated_field"]
                result["progress"] = resolution["progress"]
            elif not resolution["ok"]:
                result["error"] = resolution["error"]

            print("\n最终结果：")
            print(json.dumps(result, ensure_ascii=False, indent=4))
            return

        if agent_mode == "llm":
            # 千问决定何时调用只读工具，程序负责执行并限制工具权限。
            loop_result = run_qwen_agent_loop(
                username=username,
                target_role=user_profile["target_role"],
                progress_file="study_progress.json",
                get_progress_tool=get_study_progress
            )
        elif agent_mode == "rule":
            # 无网络或不希望产生费用时，可继续使用原有规则循环。
            loop_result = run_agent_loop(username, "study_progress.json")
        else:
            loop_result = {
                "ok": False,
                "error": "CAREER_AGENT_MODE只能是llm或rule。",
                "used_tools": [],
                "agent_loop": None
            }

        # 循环失败时也输出合法 JSON，并保留停止原因和执行轨迹。
        if not loop_result["ok"]:
            result = {
                "username": username,
                "target_role": user_profile["target_role"],
                "used_tools": loop_result.get("used_tools", []),
                "agent_loop": loop_result.get("agent_loop"),
                "model": loop_result.get("model"),
                "llm_usage": loop_result.get("llm_usage"),
                "error": loop_result["error"]
            }
            print(json.dumps(result, ensure_ascii=False, indent=4))
            return

        # result 是最终输出层：组合用户标识、目标岗位和加工后的建议。
        result = {
            "username": username,
            "target_role": user_profile["target_role"],
            "used_tools": loop_result["used_tools"],
            "agent_loop": loop_result["agent_loop"],
            "model": loop_result.get("model"),
            "llm_usage": loop_result.get("llm_usage"),
            "advice": loop_result["advice"]
        }

        # ensure_ascii=False 保留中文；indent=4 让 JSON 便于阅读。
        print(json.dumps(result, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    # 只有直接运行 main.py 时才启动；导入函数做测试时不会询问用户名。
    main()
