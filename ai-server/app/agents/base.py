"""단일 Agent 공통 구현. 시스템 프롬프트와 Tool 세트만 바꾸면 다른 역할의 Agent가 된다.
LangGraph 노드 안에서 Worker 하나의 서술 단계를 맡는다.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from ..config import settings
from ..llm.call_log import LLMCallLogger
from ..llm.factory import active_model_name, get_llm_client
from ..schemas.agent import AgentResult, ToolCallTrace
from .tool_adapter import build_langchain_tools

logger = logging.getLogger(__name__)

# 인용: 문단 pid {접수번호14}:{섹션}:{해시} · dart:{접수번호} · market-data:{종목코드}
CITATION_RE = re.compile(r"\[((?:\d{14}:[\w\-]+:T?[0-9a-f]{8}(?:-\d+)?)|(?:dart:\d{14})|(?:market-data:\d{6}))\]")


def extract_citations(text: str) -> List[str]:
    out: List[str] = []
    for m in CITATION_RE.finditer(text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def collect_citations(answer: str, steps: List[Any]) -> List[str]:
    """인용은 Tool이 실제 돌려준 값에서 모은다. 답변 본문에서 긁으면 모델이 형식을 어길 때
    실제로 근거를 조회했는데도 기록이 빈다. 답변에만 있고 Tool 결과에 없는 인용은 지어낸 것이라 버린다."""
    from_tools: List[str] = []
    for _, observation in steps:
        for c in extract_citations(str(observation)):
            if c not in from_tools:
                from_tools.append(c)
    return from_tools


class SingleAgent:
    def __init__(self, agent_id: str, system_prompt: str, tool_names: List[str], description: str = "") -> None:
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.tool_names = tool_names
        self.description = description

    async def run(self, query: str, *, user_id: str, scope: List[str]) -> AgentResult:
        started = time.time()
        # [보안] 권한 정보는 여기서 한 번만 주입된다. 이후 LLM은 손대지 못한다
        tools = build_langchain_tools(self.tool_names, agent_id=self.agent_id, user_id=user_id, scope=scope)
        prompt = ChatPromptTemplate.from_messages([("system", self.system_prompt), ("human", "{input}"),
                                                   MessagesPlaceholder("agent_scratchpad")])
        executor = AgentExecutor(
            agent=create_tool_calling_agent(get_llm_client().as_chat_model(), tools, prompt), tools=tools,
            max_iterations=settings.agent_max_iterations,          # [통제] 반복 상한
            max_execution_time=settings.agent_timeout_seconds,     # [통제] 시간 상한
            return_intermediate_steps=True, handle_parsing_errors=True)
        call_logger = LLMCallLogger(provider=settings.llm_provider, model=active_model_name(), agent_id=self.agent_id)
        try:
            raw: Dict[str, Any] = await executor.ainvoke({"input": query}, config={"callbacks": [call_logger]})
        except Exception as e:
            logger.exception("agent failed: %s", self.agent_id)
            return AgentResult(agentId=self.agent_id, ok=False, answer="", stoppedReason=f"{type(e).__name__}: {e}",
                               elapsedMs=int((time.time() - started) * 1000))
        steps = raw.get("intermediate_steps", [])
        answer = str(raw.get("output", ""))
        return AgentResult(
            agentId=self.agent_id, ok=True, answer=answer, citations=collect_citations(answer, steps),
            toolCalls=[ToolCallTrace(tool=a.tool, agentId=self.agent_id,
                                     args=a.tool_input if isinstance(a.tool_input, dict) else {"input": a.tool_input},
                                     resultSummary=str(o)[:200]) for a, o in steps],
            stoppedReason="MAX_ITERATIONS" if len(steps) >= settings.agent_max_iterations else None,
            elapsedMs=int((time.time() - started) * 1000))
