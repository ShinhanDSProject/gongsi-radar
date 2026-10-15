"""Ollama 구현체. 폐쇄망 모드의 기본 provider.

인터페이스는 6장 `LLMClient` 그대로다. Agent도 그래프도 이 파일을 알지 못한다 —
`LLM_PROVIDER=ollama` 한 줄로 갈아 끼워지는 것이 6장에서 추상화를 먼저 만든 이유다.

[중요] `as_chat_model()`이 Tool Calling을 지원해야 6·7장이 무손상으로 돈다.
       `create_tool_calling_agent`가 `bind_tools`를 부르는데, 이걸 지원하지 않는
       모델을 물리면 Agent 루프가 통째로 죽는다. Qwen 2.5는 지원한다.
"""
from __future__ import annotations
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from ..config import settings
from .base import LLMClient


class OllamaAdapter(LLMClient):
    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self._model = ChatOllama(
            model=model or settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,                  # 감사 재현성을 위해 0으로 고정
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        resp = await self._model.ainvoke(messages, **kwargs)
        return str(resp.content)

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        async for chunk in self._model.astream(messages, **kwargs):
            if chunk.content:
                yield str(chunk.content)

    def as_chat_model(self) -> BaseChatModel:
        return self._model
