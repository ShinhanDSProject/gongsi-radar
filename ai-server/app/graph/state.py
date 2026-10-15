"""LangGraph 실행 전체가 공유하는 상태. 노드는 State 전체가 아니라 자기가 채울 키만 dict로 돌려준다.

radar 파이프라인의 무거운 상태(파싱한 문서·계정·변경 문단)는 여기 넣지 않고 radar 세션에 둔다.
State에는 Worker가 서로 넘기는 것(지시·서술·인용·검토 결과)만 둔다.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from ..schemas.agent import AgentResult


def _merge_unique(left: List[str], right: List[str]) -> List[str]:
    """인용은 근거 목록이라 중복을 지운다. 반려로 재실행돼도 한 번만 담긴다."""
    out = list(left)
    for x in right:
        if x not in out:
            out.append(x)
    return out


class AnalysisState(TypedDict, total=False):
    # ---- 입력: 실행 내내 바뀌지 않는다 ----
    job_id: str
    request_id: int
    user_id: str
    scope: List[str]
    target: Dict[str, Any]                      # {"company", "bsns_year", "reprt_code"}
    query: Optional[str]                        # 관심 질문(입력 필터를 통과해 마스킹된 것)

    # ---- Manager 계획 ----
    plan: List[str]
    tasks: Dict[str, str]

    # ---- Worker 산출물 ----
    disclosure: Optional[AgentResult]
    financial: Optional[AgentResult]
    review: Optional[Dict[str, Any]]            # {"passed", "issues", "nextStep", "rejected"}
    report: Optional[Dict[str, Any]]

    # ---- 누적 ----
    # [감사] reducer를 빼면 마지막 Worker의 것만 남아 기록이 사라진다
    citations: Annotated[List[str], _merge_unique]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]

    # ---- 반려 루프 통제 ----
    revision: int
