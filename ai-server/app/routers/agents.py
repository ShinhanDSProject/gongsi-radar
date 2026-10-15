"""개발/디버깅용 Agent 직접 실행 엔드포인트.
운영에서는 /ai/analyses를 통해서만 호출된다. Spring이 Senior만 프록시한다.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException

from ..agents.definitions import AGENTS, get_agent
from ..deps import require_user_id, verify_internal_key
from ..llm.call_log import llm_call_log
from ..safety.context import set_request_uid
from ..schemas.agent import AgentResult, AgentRunRequest

router = APIRouter(prefix="/ai/agents", tags=["agents"])


@router.get("", dependencies=[Depends(verify_internal_key)])
def list_agents() -> List[Dict[str, Any]]:
    return [
        {"agentId": a.agent_id, "description": a.description, "tools": a.tool_names}
        for a in AGENTS.values()
    ] + [
        # Manager와 Report Writer는 Tool이 없어 SingleAgent가 아니다. 목록에는 실행 단위로 보인다
        {"agentId": "manager", "description": "분석 요청을 담당자별 지시로 나눈다", "tools": []},
        {"agentId": "report_writer", "description": "검증된 사실로 리포트 본문을 쓴다", "tools": []},
    ]


@router.post("/{agent_id}/run", dependencies=[Depends(verify_internal_key)],
             response_model=AgentResult)
async def run_agent(
    agent_id: str,
    req: AgentRunRequest,
    user_id: str = Depends(require_user_id),
    x_request_id: str = Header(default=""),) -> AgentResult:
    # 이 경로로 부른 LLM 호출도 llm_invocation_log에 request_uid를 달고 남게 한다
    set_request_uid(x_request_id or None)
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return await agent.run(req.query, user_id=user_id, scope=req.scope)


@router.get("/llm-calls/recent", dependencies=[Depends(verify_internal_key)])
def recent_llm_calls() -> List[Dict[str, Any]]:
    """LLM 호출 기록. /ai/tools/calls/recent 와 짝을 이룬다.
    provider별 비교는 llm_invocation_log를 직접 조회한다.
    """
    return [r.__dict__ for r in llm_call_log.recent()]