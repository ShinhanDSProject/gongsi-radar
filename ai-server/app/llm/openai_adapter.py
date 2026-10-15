"""OpenAI 구현체. 개발 단계에서 쓰는 외부 provider."""
from __future__ import annotations
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..config import settings
from .base import LLMClient


class OpenAIAdapter(LLMClient):
    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        # [보안] ALLOW_EXTERNAL_LLM 검사는 10장에서 factory로 올렸다.
        #        provider가 늘어도 막는 자리가 하나여야 빠뜨리지 않는다
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY가 비어 있다. LLM_PROVIDER=mock 으로 전환하거나 키를 설정한다.")

        self._model = ChatOpenAI(
            model=model or settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=temperature,                      # 감사 재현성을 위해 0으로 고정
            timeout=settings.agent_timeout_seconds,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        resp = await self._model.ainvoke(messages, **kwargs)
        return str(resp.content)

    # 비동기 제너레이터이므로 async def로 구현한다 (반환형은 AsyncIterator[str])
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        async for chunk in self._model.astream(messages, **kwargs):
            if chunk.content:
                yield str(chunk.content)

    def as_chat_model(self) -> BaseChatModel:
        return self._model