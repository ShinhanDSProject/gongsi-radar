from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str = Field(..., max_length=1000)
    scope: List[str] = Field(default_factory=lambda: ["RAG_READ"])
    topK: int = 5
    minScore: float = 0.3
    trustLevels: Optional[List[str]] = None
    corpCode: Optional[str] = None
    rceptNo: Optional[str] = None


class RagSearchHit(BaseModel):
    chunkId: str                     # 문단 인용 ID {rcept_no}:{섹션 키}:{해시}
    docId: str                       # dart:{rcept_no}
    title: str
    source: str
    publishedAt: str
    content: str
    score: float
    trustLevel: str
    sectionPath: str = ""


class RagSearchResponse(BaseModel):
    items: List[RagSearchHit]
    total: int
