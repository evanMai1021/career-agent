"""CareerAgent V1.3 本地只读 HTTP API。

数据文件路径只允许由服务端创建应用时注入，HTTP 客户端不能指定。
"""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator

from job_analysis_agent import build_trusted_facts
from job_matching import (
    get_candidate_evidence,
    get_job_requirements,
    match_job_requirements,
)


DEFAULT_JOBS_FILE = Path(__file__).resolve().parent / "jobs.json"
DEFAULT_EVIDENCE_FILE = (
    Path(__file__).resolve().parent / "candidate_evidence.json"
)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class JobRequirementResponse(BaseModel):
    requirement_id: str
    skill_id: str
    description: str
    category: Literal["required", "preferred"]
    priority: Literal[1, 2, 3]


class JobRequirementsResponse(BaseModel):
    job_id: str
    title: str
    requirements: list[JobRequirementResponse]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    job_id: str

    @field_validator("username", "job_id")
    @classmethod
    def validate_nonempty_scope(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("必须是非空字符串。")
        return value.strip()


class MatchResponse(JobRequirementResponse):
    status: Literal["matched", "partial", "missing", "unverified"]
    related_evidence_ids: list[str]


class TrustedFactResponse(BaseModel):
    requirement_id: str
    skill_id: str
    status: Literal["matched", "partial", "missing", "unverified"]
    related_evidence_ids: list[str]
    verified_evidence_ids: list[str]
    unverified_evidence_ids: list[str]
    origin: Literal["python_deterministic_match"]


class AnalysisResponse(BaseModel):
    username: str
    job_id: str
    title: str
    analysis_mode: Literal["offline_deterministic"]
    model_generated: Literal[False]
    matches: list[MatchResponse]
    trusted_facts: list[TrustedFactResponse]


def create_app(
    *,
    jobs_file: Path | None = None,
    evidence_file: Path | None = None,
) -> FastAPI:
    """创建本地 API；测试可从 Python 注入文件，HTTP 请求不可指定。"""
    selected_jobs_file = (
        Path(jobs_file) if jobs_file is not None else DEFAULT_JOBS_FILE
    )
    selected_evidence_file = (
        Path(evidence_file)
        if evidence_file is not None
        else DEFAULT_EVIDENCE_FILE
    )
    api = FastAPI(title="CareerAgent Local API", version="1.3.0")

    @api.get("/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        return HealthResponse(status="ok")

    @api.get(
        "/jobs/{job_id}/requirements",
        response_model=JobRequirementsResponse,
    )
    def read_job_requirements(
        job_id: str,
        request: Request,
    ) -> JobRequirementsResponse:
        if request.query_params:
            raise HTTPException(status_code=422, detail="不接受查询参数。")
        if not job_id.strip():
            raise HTTPException(status_code=422, detail="岗位ID不能为空。")

        result = get_job_requirements(job_id, selected_jobs_file)
        if not result["ok"]:
            if result["error"].startswith("未找到岗位："):
                raise HTTPException(status_code=404, detail="岗位不存在。")
            raise HTTPException(status_code=503, detail="岗位数据暂不可用。")

        return JobRequirementsResponse.model_validate(result)

    @api.post("/analyses", response_model=AnalysisResponse)
    def create_analysis(
        payload: AnalysisRequest,
        request: Request,
    ) -> AnalysisResponse:
        """只运行 Python 确定性匹配，不调用模型，也不写入文件。"""
        if request.query_params:
            raise HTTPException(status_code=422, detail="不接受查询参数。")

        job_result = get_job_requirements(
            payload.job_id,
            selected_jobs_file,
        )
        if not job_result["ok"]:
            if job_result["error"].startswith("未找到岗位："):
                raise HTTPException(status_code=404, detail="岗位不存在。")
            raise HTTPException(status_code=503, detail="岗位数据暂不可用。")

        evidence_result = get_candidate_evidence(
            payload.username,
            selected_evidence_file,
        )
        if not evidence_result["ok"]:
            if evidence_result["error"].startswith("未找到用户："):
                raise HTTPException(status_code=404, detail="候选人不存在。")
            raise HTTPException(
                status_code=503,
                detail="候选人证据数据暂不可用。",
            )

        try:
            matches = match_job_requirements(
                {
                    "job_id": job_result["job_id"],
                    "title": job_result["title"],
                    "requirements": job_result["requirements"],
                },
                {
                    "username": evidence_result["username"],
                    "evidence": evidence_result["evidence"],
                },
            )
            trusted_facts = build_trusted_facts(
                matches,
                evidence_result["evidence"],
            )
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=503,
                detail="分析数据暂不可用。",
            ) from None

        return AnalysisResponse.model_validate(
            {
                "username": evidence_result["username"],
                "job_id": job_result["job_id"],
                "title": job_result["title"],
                "analysis_mode": "offline_deterministic",
                "model_generated": False,
                "matches": matches,
                "trusted_facts": trusted_facts,
            }
        )

    return api


app = create_app()
