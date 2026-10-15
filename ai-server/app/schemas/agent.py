from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    query: str = Field(..., max_length=4000)
    scope: List[str] = Field(default_factory=list)


class ToolCallTrace(BaseModel):
    """Agent가 어떤 Tool을 어떤 인자로 불렀는지 — 감사의 최소 단위."""
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    resultSummary: str = ""
    agentId: Optional[str] = None


class AgentResult(BaseModel):
    agentId: str
    ok: bool
    answer: str
    citations: List[str] = Field(default_factory=list)
    toolCalls: List[ToolCallTrace] = Field(default_factory=list)
    stoppedReason: Optional[str] = None            # MAX_ITERATIONS 등 중단 사유
    elapsedMs: int = 0
