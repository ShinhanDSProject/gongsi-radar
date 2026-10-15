"""API 키 없이 Agent 전 구간을 재현하기 위한 Mock LLM.

답변만 흉내 내지 않고 tool_calls를 만들어 실제로 Tool Gateway를 거치게 한다. 동작이 결정적이라 테스트에도 쓴다.
공시레이더 Worker에게 주는 지시문 첫 줄에는 항상 `[분석 대상] company=… bsns_year=… reprt_code=…`가 들어 있다.
Mock은 그 줄에서 Tool 인자를 채운다 — 실제 모델이 하는 일(지시문에서 인자 읽기)과 같은 경로다.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from .base import LLMClient

_TARGET_RE = re.compile(r"company=(\S+)\s+bsns_year=(\d{4})\s+reprt_code=(\d{5})")


def parse_target(text: str) -> Dict[str, Any]:
    m = _TARGET_RE.search(text or "")
    if not m:
        return {}
    return {"company": m.group(1), "bsns_year": int(m.group(2)), "reprt_code": m.group(3)}


class MockChatModel(BaseChatModel):
    """규칙 기반 가짜 chat model.
    - ToolMessage가 없으면: 묶인 Tool을 차례로(최대 2개) 부르는 tool_calls
    - ToolMessage가 있으면: 관찰 결과를 정리한 최종 답변(인용은 관찰 결과에 있던 것만)
    """

    bound_tools: List[BaseTool] = []

    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "MockChatModel":
        return MockChatModel(bound_tools=list(tools))

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any) -> ChatResult:
        observations = [m for m in messages if isinstance(m, ToolMessage)]
        if self.bound_tools and not observations:
            text = self._user_text(messages)
            calls = [{"name": t.name, "args": self._build_args(t, text), "id": f"call_{uuid.uuid4().hex[:8]}"}
                     for t in self.bound_tools[:2]]
            message = AIMessage(content="", tool_calls=calls)
        else:
            names = {c["id"]: c["name"] for m in messages if isinstance(m, AIMessage) for c in (m.tool_calls or [])}
            lines = [f"- {m.name or names.get(m.tool_call_id, 'tool')}: {str(m.content)[:400]}" for m in observations]
            message = AIMessage(content="[mock 응답] 조회한 자료를 정리하면 다음과 같다.\n"
                                        + ("\n".join(lines) or "조회된 자료가 없다."))
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _user_text(messages: List[BaseMessage]) -> str:
        for m in reversed(messages):
            if m.type == "human":
                return str(m.content)
        return ""

    @staticmethod
    def _build_args(tool: BaseTool, text: str) -> dict:
        target = parse_target(text)
        fields = tool.args_schema.model_fields if tool.args_schema else {}
        args: Dict[str, Any] = {k: v for k, v in target.items() if k in fields}
        if "query" in fields:
            args["query"] = re.sub(r"\[분석 대상\][^\n]*\n?", "", text)[:100] or "주요 변경"
        if "corp_code" in fields and "company" in target:
            args["corp_code"] = target["company"]
        if "stock_code" in fields and "company" in target:
            args["stock_code"] = target["company"]
        return args


class MockAdapter(LLMClient):
    """단발 호출(chat)은 고정 문구. Manager 계획은 JSON을 내지 않으므로 그래프가 전체 실행으로 폴백한다."""

    def __init__(self) -> None:
        self._model = MockChatModel()

    async def chat(self, messages: list[dict], **kwargs) -> str:
        last = messages[-1]["content"] if messages else ""
        if "리포트 작성자" in json.dumps(messages, ensure_ascii=False):
            return ("[mock 응답] LLM_PROVIDER=mock 상태라 서술 본문은 규칙 모드 요약으로 대신한다.\n\n"
                    + last.split("[검증된 사실]", 1)[-1].strip()[:2000])
        return "[mock 응답] LLM_PROVIDER=mock 상태다. 외부 모델 호출은 일어나지 않았다."

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        yield await self.chat(messages, **kwargs)

    def as_chat_model(self) -> BaseChatModel:
        return self._model
