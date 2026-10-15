"""千问模型接入与受控工具调用循环。"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI


QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen3.8-flash"

# 复习任务在工具参数和建议来源中复用同一份结构约束。
REVIEW_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_id": {"type": "integer"},
        "title": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {"type": "string"}
        },
        "status": {"type": "string"}
    },
    "required": ["problem_id", "title", "topics", "status"],
    "additionalProperties": False
}

# 建议必须携带结构化数据来源，便于 Python 与工具结果逐项核对。
ADVICE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "career_advice",
        "description": "CareerAgent 根据学习进度生成的三类建议",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "python": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "reason": {"type": "string"},
                        "sources": {
                            "type": "object",
                            "properties": {
                                "python_progress": {"type": "string"}
                            },
                            "required": ["python_progress"],
                            "additionalProperties": False
                        }
                    },
                    "required": ["task", "reason", "sources"],
                    "additionalProperties": False
                },
                "leetcode": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "reason": {"type": "string"},
                        "sources": {
                            "type": "object",
                            "properties": {
                                "leetcode_topic": {"type": "string"},
                                "review_tasks": {
                                    "type": "array",
                                    "items": REVIEW_TASK_SCHEMA
                                }
                            },
                            "required": ["leetcode_topic", "review_tasks"],
                            "additionalProperties": False
                        }
                    },
                    "required": ["task", "reason", "sources"],
                    "additionalProperties": False
                },
                "agent": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "reason": {"type": "string"},
                        "sources": {
                            "type": "object",
                            "properties": {
                                "agent_progress": {"type": "string"}
                            },
                            "required": ["agent_progress"],
                            "additionalProperties": False
                        }
                    },
                    "required": ["task", "reason", "sources"],
                    "additionalProperties": False
                }
            },
            "required": ["python", "leetcode", "agent"],
            "additionalProperties": False
        }
    }
}

# 第一版只向模型开放只读工具。文件路径不会交给模型决定。
STUDY_PROGRESS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_study_progress",
        "description": "按用户名读取脱敏的 Python、LeetCode 和 Agent 学习进度。",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "需要查询的用户名"
                }
            },
            "required": ["username"],
            "additionalProperties": False
        }
    }
}

# 写入工具在提案阶段只作为参数结构交给模型，Python 不会执行它。
UPDATE_STUDY_PROGRESS_TOOL = {
    "type": "function",
    "function": {
        "name": "update_study_progress",
        "description": "根据用户明确要求，提出一个学习进度字段更新方案。",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "需要更新的当前用户名"
                },
                "field": {
                    "type": "string",
                    "enum": [
                        "python_progress",
                        "leetcode_topic",
                        "agent_progress",
                        "review_tasks"
                    ]
                },
                "new_value": {
                    "description": "字段的新值；进度字段为字符串，复习任务为对象列表。",
                    "oneOf": [
                        {"type": "string"},
                        {
                            "type": "array",
                            "items": REVIEW_TASK_SCHEMA
                        }
                    ]
                }
            },
            "required": ["username", "field", "new_value"],
            "additionalProperties": False
        }
    }
}


def create_qwen_client():
    """从本地环境变量读取密钥并创建千问兼容客户端。"""
    # load_dotenv() 只把本地 .env 加载到进程环境，不会打印或上传密钥。
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未配置DASHSCOPE_API_KEY，请检查本地.env文件。")

    return OpenAI(api_key=api_key, base_url=QWEN_BASE_URL)


def _empty_usage():
    """创建可累加的 Token 用量记录。"""
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }


def _add_usage(total_usage, response):
    """累加一次模型响应中的 Token 用量；测试替身可以不提供 usage。"""
    usage = getattr(response, "usage", None)
    if usage is None:
        return

    total_usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    total_usage["completion_tokens"] += (
        getattr(usage, "completion_tokens", 0) or 0
    )
    total_usage["total_tokens"] += getattr(usage, "total_tokens", 0) or 0


def _validate_advice(advice, study_progress):
    """验证建议结构，并确认模型声明的来源与工具结果完全一致。"""
    if not isinstance(advice, dict) or not isinstance(study_progress, dict):
        return False

    for category in ("python", "leetcode", "agent"):
        item = advice.get(category)
        if not isinstance(item, dict):
            return False
        if set(item) != {"task", "reason", "sources"}:
            return False
        if not all(
            isinstance(item[field], str) and item[field].strip()
            for field in ("task", "reason")
        ):
            return False

    expected_sources = {
        "python": {
            "python_progress": study_progress.get("python_progress")
        },
        "leetcode": {
            "leetcode_topic": study_progress.get("leetcode_topic"),
            "review_tasks": study_progress.get("review_tasks")
        },
        "agent": {
            "agent_progress": study_progress.get("agent_progress")
        }
    }
    return all(
        advice[category]["sources"] == expected_sources[category]
        for category in ("python", "leetcode", "agent")
    )


def _model_error_result(model, max_steps, trace, used_tools, usage, error):
    """把模型异常转换成稳定、可序列化的错误结果。"""
    error_code = getattr(error, "code", None) or type(error).__name__
    return {
        "ok": False,
        "error": f"千问模型调用失败：{error_code}",
        "used_tools": used_tools,
        "model": model,
        "llm_usage": usage,
        "agent_loop": {
            "mode": "llm_tool_calling",
            "max_steps": max_steps,
            "stop_reason": "model_error",
            "trace": trace
        }
    }


def _update_proposal_error(model, usage, trace, stop_reason, message):
    """创建不会误报工具已执行的写入提案错误结果。"""
    return {
        "ok": False,
        "error": message,
        "used_tools": [],
        "requested_tools": [],
        "model": model,
        "llm_usage": usage,
        "agent_loop": {
            "mode": "llm_update_proposal",
            "max_steps": 1,
            "stop_reason": stop_reason,
            "trace": trace
        }
    }


def run_qwen_update_proposal(
    username,
    target_role,
    user_request,
    validate_update,
    client=None,
    model=DEFAULT_QWEN_MODEL
):
    """让千问生成写入参数提案；本函数绝不执行本地更新工具。"""
    usage = _empty_usage()
    trace = []

    if not isinstance(user_request, str) or not user_request.strip():
        return _update_proposal_error(
            model, usage, trace, "invalid_request", "更新要求不能为空。"
        )

    username = username.strip()
    if client is None:
        try:
            client = create_qwen_client()
        except RuntimeError as error:
            error_code = getattr(error, "code", None) or type(error).__name__
            return _update_proposal_error(
                model,
                usage,
                trace,
                "model_error",
                f"千问模型调用失败：{error_code}"
            )

    messages = [
        {
            "role": "system",
            "content": (
                "你是CareerAgent的写入规划器。用户已经明确提出更新要求。"
                "请调用update_study_progress生成一份参数提案，但不要声称已经写入。"
                "只能更新当前用户名，只能选择工具schema允许的字段。"
                "提案会由Python校验并展示给用户确认，确认前不会修改文件。"
            )
        },
        {
            "role": "user",
            "content": (
                f"当前用户：{username}；目标岗位：{target_role}；"
                f"明确更新要求：{user_request.strip()}"
            )
        }
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[UPDATE_STUDY_PROGRESS_TOOL],
            tool_choice={
                "type": "function",
                "function": {"name": "update_study_progress"}
            },
            parallel_tool_calls=False,
            max_completion_tokens=500,
            temperature=0,
            extra_body={"enable_thinking": False}
        )
    except Exception as error:
        error_code = getattr(error, "code", None) or type(error).__name__
        trace.append({
            "step": 1,
            "action": "qwen_update_proposal",
            "status": "error"
        })
        return _update_proposal_error(
            model,
            usage,
            trace,
            "model_error",
            f"千问模型调用失败：{error_code}"
        )

    _add_usage(usage, response)
    tool_calls = response.choices[0].message.tool_calls or []
    if len(tool_calls) != 1:
        trace.append({
            "step": 1,
            "action": "qwen_update_proposal",
            "status": "error"
        })
        return _update_proposal_error(
            model,
            usage,
            trace,
            "invalid_model_output",
            "千问没有返回唯一的写入工具提案。"
        )

    tool_call = tool_calls[0]
    if tool_call.function.name != "update_study_progress":
        return _update_proposal_error(
            model,
            usage,
            trace,
            "unauthorized_tool",
            f"模型请求了未授权工具：{tool_call.function.name}"
        )

    try:
        arguments = json.loads(tool_call.function.arguments)
        requested_username = arguments["username"].strip()
        field = arguments["field"]
        new_value = arguments["new_value"]
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return _update_proposal_error(
            model,
            usage,
            trace,
            "invalid_tool_arguments",
            "模型提供的写入参数无效。"
        )

    if requested_username != username:
        return _update_proposal_error(
            model,
            usage,
            trace,
            "tool_scope_violation",
            "模型请求的用户名与当前用户不一致。"
        )

    validation_error = validate_update(field, new_value)
    if validation_error:
        return _update_proposal_error(
            model,
            usage,
            trace,
            "invalid_update_proposal",
            validation_error
        )

    trace.append({
        "step": 1,
        "action": "qwen_update_proposal",
        "status": "confirmation_required"
    })
    return {
        "ok": True,
        "status": "confirmation_required",
        "used_tools": [],
        "requested_tools": ["update_study_progress"],
        "model": model,
        "llm_usage": usage,
        "write_proposal": {
            "username": username,
            "field": field,
            "new_value": new_value
        },
        "agent_loop": {
            "mode": "llm_update_proposal",
            "max_steps": 1,
            "stop_reason": "confirmation_required",
            "trace": trace
        }
    }


def run_qwen_agent_loop(
    username,
    target_role,
    progress_file,
    get_progress_tool,
    max_steps=3,
    client=None,
    model=DEFAULT_QWEN_MODEL
):
    """让千问在有限步数内选择只读工具，并生成结构化学习建议。"""
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        return {"ok": False, "error": "max_steps必须是正整数。"}

    username = username.strip()
    trace = []
    used_tools = []
    usage = _empty_usage()
    study_progress = None

    if client is None:
        try:
            client = create_qwen_client()
        except RuntimeError as error:
            return _model_error_result(
                model, max_steps, trace, used_tools, usage, error
            )

    messages = [
        {
            "role": "system",
            "content": (
                "你是CareerAgent。请根据用户的求职目标和学习进度，"
                "生成Python、LeetCode、Agent三类具体建议。"
                "在没有学习进度时，应先调用get_study_progress；"
                "获得工具结果后再输出符合指定JSON Schema的建议。"
                "最终JSON最外层只能包含python、leetcode、agent三个字段。"
                "task说明具体做什么，reason说明它与当前进度的关系。"
                "不得虚构用户已经完成的学习内容。"
                "review_tasks中的topics是每道复习题经过本地校验的真实专题；"
                "leetcode_topic只是当前主线专题，不得用它覆盖每道题自己的topics。"
                "reason只能引用工具结果中存在的事实，不得强行建立未经提供的技术关联。"
                "每类建议都必须在sources中原样复制对应工具数据："
                "Python复制python_progress，Agent复制agent_progress，"
                "LeetCode复制leetcode_topic和完整review_tasks，不得改写题目来源。"
            )
        },
        {
            "role": "user",
            "content": f"请为用户{username}生成学习建议，目标岗位是{target_role}。"
        }
    ]

    for step in range(1, max_steps + 1):
        request_options = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": 800,
            "temperature": 0.2,
            "extra_body": {"enable_thinking": False}
        }

        if used_tools:
            # 工具完成后进入生成阶段，不再允许模型重复调用工具。
            request_options["response_format"] = ADVICE_RESPONSE_FORMAT
        else:
            # 第一轮只让模型决定是否需要读取进度。
            request_options.update({
                "tools": [STUDY_PROGRESS_TOOL],
                "tool_choice": "auto",
                "parallel_tool_calls": False
            })

        try:
            response = client.chat.completions.create(**request_options)
        except Exception as error:  # SDK 会提供具体错误类型和错误码。
            trace.append({
                "step": step,
                "action": "qwen_decision",
                "status": "error"
            })
            return _model_error_result(
                model, max_steps, trace, used_tools, usage, error
            )

        _add_usage(usage, response)
        assistant_output = response.choices[0].message
        tool_calls = assistant_output.tool_calls or []

        if tool_calls:
            trace.append({
                "step": step,
                "action": "qwen_decision",
                "status": "tool_call"
            })

            # 将模型的工具请求加入对话，再把本地执行结果作为 tool 消息返回。
            assistant_message = {
                "role": "assistant",
                "content": assistant_output.content or "",
                "tool_calls": []
            }
            for tool_call in tool_calls:
                assistant_message["tool_calls"].append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
            messages.append(assistant_message)

            for tool_call in tool_calls:
                if tool_call.function.name != "get_study_progress":
                    return {
                        "ok": False,
                        "error": f"模型请求了未授权工具：{tool_call.function.name}",
                        "used_tools": used_tools,
                        "model": model,
                        "llm_usage": usage,
                        "agent_loop": {
                            "mode": "llm_tool_calling",
                            "max_steps": max_steps,
                            "stop_reason": "unauthorized_tool",
                            "trace": trace
                        }
                    }

                try:
                    arguments = json.loads(tool_call.function.arguments)
                    requested_username = arguments["username"].strip()
                except (json.JSONDecodeError, KeyError, AttributeError):
                    return {
                        "ok": False,
                        "error": "模型提供的工具参数无效。",
                        "used_tools": used_tools,
                        "model": model,
                        "llm_usage": usage,
                        "agent_loop": {
                            "mode": "llm_tool_calling",
                            "max_steps": max_steps,
                            "stop_reason": "invalid_tool_arguments",
                            "trace": trace
                        }
                    }

                # 模型只能读取当前已验证用户，不能改成另一个用户名。
                if requested_username != username:
                    return {
                        "ok": False,
                        "error": "模型请求的用户名与当前用户不一致。",
                        "used_tools": used_tools,
                        "model": model,
                        "llm_usage": usage,
                        "agent_loop": {
                            "mode": "llm_tool_calling",
                            "max_steps": max_steps,
                            "stop_reason": "tool_scope_violation",
                            "trace": trace
                        }
                    }

                tool_result = get_progress_tool(username, progress_file)
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
                        "model": model,
                        "llm_usage": usage,
                        "agent_loop": {
                            "mode": "llm_tool_calling",
                            "max_steps": max_steps,
                            "stop_reason": "tool_error",
                            "trace": trace
                        }
                    }

                study_progress = tool_result["progress"]
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        tool_result, ensure_ascii=False, separators=(",", ":")
                    )
                })
            continue

        # 没有工具请求时，模型应当已经返回最终结构化建议。
        try:
            advice = json.loads(assistant_output.content or "")
        except json.JSONDecodeError:
            advice = None

        if not _validate_advice(advice, study_progress):
            trace.append({
                "step": step,
                "action": "qwen_structured_advice",
                "status": "error"
            })
            return {
                "ok": False,
                "error": "千问没有返回符合约定结构的建议。",
                "used_tools": used_tools,
                "model": model,
                "llm_usage": usage,
                "agent_loop": {
                    "mode": "llm_tool_calling",
                    "max_steps": max_steps,
                    "stop_reason": "invalid_model_output",
                    "trace": trace
                }
            }

        trace.append({
            "step": step,
            "action": "qwen_structured_advice",
            "status": "success"
        })
        return {
            "ok": True,
            "used_tools": used_tools,
            "model": model,
            "llm_usage": usage,
            "advice": advice,
            "agent_loop": {
                "mode": "llm_tool_calling",
                "max_steps": max_steps,
                "stop_reason": "completed",
                "trace": trace
            }
        }

    return {
        "ok": False,
        "error": "LLM Agent循环达到最大步数，任务未完成。",
        "used_tools": used_tools,
        "model": model,
        "llm_usage": usage,
        "agent_loop": {
            "mode": "llm_tool_calling",
            "max_steps": max_steps,
            "stop_reason": "max_steps_reached",
            "trace": trace
        }
    }
