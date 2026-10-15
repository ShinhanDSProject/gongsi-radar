from abc import ABC, abstractmethod
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str: ...

    @abstractmethod
    def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    def as_chat_model(self) -> BaseChatModel:
        """LangChain Agent에 주입할 chat model. Tool Calling을 지원해야 한다."""
