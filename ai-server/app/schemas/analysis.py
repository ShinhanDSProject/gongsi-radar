"""분석 요청·Job 모델(docs/CONTRACT.md §4). Quant-X의 ResearchRequest·JobStatus를 공시 도메인에 맞춘 것이다."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AnalysisOptions(BaseModel):
    demoFaultInjection: bool = False      # 시연용: 첫 시도에서 수치 오류를 넣어 반려 루프를 보여 준다


class AnalysisRequest(BaseModel):
    requestId: int
    userId: str
    company: str = Field(..., min_length=1, max_length=100)      # 종목코드·고유번호·회사명
    bsnsYear: int = Field(..., ge=2015, le=2100)
    reprtCode: Literal["11011", "11012", "11013", "11014"] = "11011"
    query: Optional[str] = Field(default=None, max_length=1000)  # 관심 질문(입력 가드레일 대상)
    scope: List[str] = Field(default_factory=list)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class JobStatus(BaseModel):
    jobId: str
    status: str                                    # RUNNING, COMPLETED, FAILED
    progress: float = 0.0
    currentStep: Optional[str] = None              # PLANNING → DISCLOSURE → FINANCIAL → REVIEW → WRITING → DONE
    result: Optional[Dict[str, Any]] = None        # {"report": RadarReport} | {"error": str}
    agentExecutions: List[Dict[str, Any]] = Field(default_factory=list)
