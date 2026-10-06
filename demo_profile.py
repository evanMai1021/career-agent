"""固定 test_user 的历史脱敏资料投影，不修改记录或推断当前掌握程度。"""

import json
from pathlib import Path

from main import get_study_progress
from job_matching import get_candidate_evidence


PROFILE_USERNAME = "test_user"


def load_demo_profile(*, users_file, progress_file, evidence_file):
    """只返回公开演示字段；文件位置只能由服务端提供。"""
    users = json.loads(Path(users_file).read_text(encoding="utf-8"))
    if not isinstance(users, dict):
        raise ValueError("用户数据无效。")
    user = users.get(PROFILE_USERNAME)
    if not isinstance(user, dict):
        raise ValueError("历史用户不存在。")
    target_role = user.get("target_role")
    if not isinstance(target_role, str) or not target_role.strip():
        raise ValueError("目标岗位无效。")
    progress = get_study_progress(PROFILE_USERNAME, progress_file)
    evidence = get_candidate_evidence(PROFILE_USERNAME, evidence_file)
    if not progress["ok"] or not evidence["ok"]:
        raise ValueError("历史资料无效。")
    groups = {
        "verified_application": [],
        "verified_learning": [],
        "unverified": [],
    }
    for item in evidence["evidence"]:
        if not item["verified"]:
            group = "unverified"
        elif item["level"] in {"project", "production"}:
            group = "verified_application"
        else:
            group = "verified_learning"
        groups[group].append(item["evidence_id"])
    return {
        "username": PROFILE_USERNAME,
        "data_kind": "historical_demo",
        "target_role": target_role,
        "study_progress": progress["progress"],
        "evidence": evidence["evidence"],
        "evidence_groups": groups,
        "source_files": ["users.json", "study_progress.json", "candidate_evidence.json"],
        "note": "历史脱敏记录，不代表当前个人能力。学习进度不自动升级为已验证证据；项目测试通过不等于用户已经独立掌握。",
    }
