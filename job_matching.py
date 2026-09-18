"""CareerAgent V0.9b 的确定性岗位匹配。

本模块只根据已验证的结构化证据计算状态，不调用大模型，也不修改数据。
"""

import json
from pathlib import Path

from job_data import (
    validate_candidate_evidence,
    validate_candidate_evidence_data,
    validate_job,
    validate_jobs_data
)


MATCHED_EVIDENCE_LEVELS = {"project", "production"}
PARTIAL_EVIDENCE_LEVELS = {"learning", "practice"}


def _load_json_data(file_path):
    """只读加载 UTF-8 JSON；失败时返回 None，由工具生成稳定错误。"""
    try:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


def get_job_requirements(job_id, jobs_file):
    """读取并返回一个已验证岗位的结构化要求。"""
    if not isinstance(job_id, str) or not job_id.strip():
        return {"ok": False, "error": "岗位ID不能为空。"}

    job_id = job_id.strip()
    jobs_data = _load_json_data(jobs_file)
    if jobs_data is None:
        return {
            "ok": False,
            "error": "无法加载岗位数据，请检查文件路径和JSON格式。"
        }

    jobs_error = validate_jobs_data(jobs_data)
    if jobs_error:
        return {"ok": False, "error": jobs_error}

    for job in jobs_data["jobs"]:
        if job["job_id"].strip() == job_id:
            return {
                "ok": True,
                "job_id": job_id,
                "title": job["title"],
                "requirements": job["requirements"]
            }

    return {"ok": False, "error": f"未找到岗位：{job_id}"}


def get_candidate_evidence(username, evidence_file):
    """读取并返回一个已验证候选人的结构化证据。"""
    if not isinstance(username, str) or not username.strip():
        return {"ok": False, "error": "用户名不能为空。"}

    username = username.strip()
    evidence_data = _load_json_data(evidence_file)
    if evidence_data is None:
        return {
            "ok": False,
            "error": "无法加载个人证据数据，请检查文件路径和JSON格式。"
        }

    evidence_error = validate_candidate_evidence_data(evidence_data)
    if evidence_error:
        return {"ok": False, "error": evidence_error}

    for candidate in evidence_data["candidates"]:
        if candidate["username"].strip() == username:
            return {
                "ok": True,
                "username": username,
                "evidence": candidate["evidence"]
            }

    return {"ok": False, "error": f"未找到用户：{username}"}


def match_job_requirements(job, candidate):
    """按已验证证据层级为每项岗位要求生成唯一匹配状态。"""
    job_error = validate_job(job)
    if job_error:
        raise ValueError(job_error)

    candidate_error = validate_candidate_evidence(candidate)
    if candidate_error:
        raise ValueError(candidate_error)

    results = []
    for requirement in job["requirements"]:
        related_evidence = [
            evidence
            for evidence in candidate["evidence"]
            if evidence["skill_id"] == requirement["skill_id"]
        ]
        verified_levels = {
            evidence["level"]
            for evidence in related_evidence
            if evidence["verified"]
        }

        if verified_levels & MATCHED_EVIDENCE_LEVELS:
            status = "matched"
        elif verified_levels & PARTIAL_EVIDENCE_LEVELS:
            status = "partial"
        elif related_evidence:
            status = "unverified"
        else:
            status = "missing"

        results.append({
            **requirement,
            "status": status,
            "related_evidence_ids": [
                evidence["evidence_id"] for evidence in related_evidence
            ]
        })

    return results
