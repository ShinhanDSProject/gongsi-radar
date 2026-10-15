"""요청·응답 모델. docs/CONTRACT.md §5의 형태를 그대로 따른다."""
from __future__ import annotations
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

PublicationStatus = Literal["PENDING", "PUBLISHED", "REJECTED", "EXPIRED", "FAILED", "SUPERSEDED"]

_HEX64 = r"^[0-9a-fA-F]{64}$"


class PublicationCreate(BaseModel):
    reportId: int
    corpCode: str = Field(..., min_length=1, max_length=16)
    corpName: str = Field(..., min_length=1, max_length=200)
    periodLabel: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    contentHash: str = Field(..., pattern=_HEX64)   # SHA-256 hex. Spring Boot가 계산한다
    submittedBy: str = Field(..., min_length=1)     # 발행 요청자. Spring Boot가 채운다
    supersedesId: Optional[str] = None              # 정정 발행이면 이전 publicationId

    @field_validator("contentHash")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class ApproveIn(BaseModel):
    """승인 의견(comment)은 받지 않는다. Core Zone에는 발행에 필요한 사실만 두고,
    누가 왜 승인했는지는 Spring Boot의 publication_queue와 감사 로그가 갖는다.
    """
    decidedBy: str = Field(..., min_length=1)
    contentHash: str = Field(..., pattern=_HEX64)   # 요청 시점 해시. 그 사이 본문이 바뀌었으면 거절

    @field_validator("contentHash")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class RejectIn(BaseModel):
    decidedBy: str = Field(..., min_length=1)
    reason: Optional[str] = Field(default=None, max_length=1000)


class PublicationOut(BaseModel):
    publicationId: str
    reportId: int
    corpCode: str
    corpName: str
    periodLabel: str
    title: str
    contentHash: str
    version: int
    supersedesId: Optional[str] = None
    status: str
    submittedBy: str
    decidedBy: Optional[str] = None
    decidedAt: Optional[str] = None
    publishedAt: Optional[str] = None
    rejectReason: Optional[str] = None
    createdAt: str
    decisionRequiredBy: str
    duplicate: bool = False                   # 같은 멱등성 키로 다시 들어온 요청인가


class PublicationListOut(BaseModel):
    items: List[PublicationOut]
    total: int
    page: int
    size: int
