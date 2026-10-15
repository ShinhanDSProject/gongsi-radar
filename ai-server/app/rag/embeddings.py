"""임베딩 Provider 추상화. LLM Adapter와 같은 패턴 — EMBEDDING_PROVIDER 하나로 바꾼다.

  ollama : 로컬 Ollama의 bge-m3(1024차원). 폐쇄망 기본값. 문서가 밖으로 나가지 않는다
  openai : text-embedding-3-small(1536차원). 외부 호출이라 ALLOW_EXTERNAL_LLM=false면 막힌다
  hash   : 문자 n-gram 해싱(512차원). 모델 없이 결정적으로 돈다 — 테스트·오프라인 시연용

[보안] 폐쇄망 모드는 임베딩도 막는다. LLM만 막고 임베딩을 내보내면 공시 원문 전문이 그대로 나간다.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import List

from langchain_core.embeddings import Embeddings

from ..config import settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def get(self) -> Embeddings: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class HashEmbeddings(Embeddings):
    """한국어 문자 2~3-gram을 해싱해 L2 정규화한 벡터. 의미 검색은 약하지만 같은 낱말이 겹치면 가깝다."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        t = "".join((text or "").split())
        for n in (2, 3):
            for i in range(max(0, len(t) - n + 1)):
                h = int.from_bytes(hashlib.blake2b(t[i:i + n].encode(), digest_size=4).digest(), "little")
                v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vec(text)


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._e = HashEmbeddings()

    def get(self) -> Embeddings:
        return self._e

    @property
    def model_name(self) -> str:
        return "hash:char-ngram-512"


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "bge-m3") -> None:
        from langchain_ollama import OllamaEmbeddings
        self._model = model
        self._e = OllamaEmbeddings(model=model, base_url=settings.ollama_base_url)

    def get(self) -> Embeddings:
        return self._e

    @property
    def model_name(self) -> str:
        return f"ollama:{self._model}"


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "text-embedding-3-small") -> None:
        from langchain_openai import OpenAIEmbeddings
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self._model = model
        self._e = OpenAIEmbeddings(model=model, api_key=settings.openai_api_key)

    def get(self) -> Embeddings:
        return self._e

    @property
    def model_name(self) -> str:
        return f"openai:{self._model}"


def build_embedding_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "openai" and not settings.allow_external_llm:
        raise RuntimeError("ALLOW_EXTERNAL_LLM=false 인데 EMBEDDING_PROVIDER=openai 다. "
                           "폐쇄망 모드에서는 ollama(bge-m3) 같은 로컬 임베딩을 쓴다.")
    if provider == "openai":
        return OpenAIEmbeddingProvider(settings.embedding_model or "text-embedding-3-small")
    if provider in ("ollama", "bge-m3", "bge"):
        return OllamaEmbeddingProvider(settings.embedding_model or "bge-m3")
    if provider == "hash":
        return HashEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {provider}")
