"""Chroma 기반 Vector Store. 운영에서는 Qdrant·pgvector로 바꿀 수 있다(메타는 MariaDB에도 있다)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document

from ..config import settings
from .embeddings import build_embedding_provider


def _slug(model_name: str) -> str:
    """`ollama:bge-m3` → `ollama_bge_m3`. Chroma 컬렉션명 제약(63자)에 맞춘다."""
    s = "".join(c if c.isalnum() else "_" for c in model_name.lower()).strip("_")
    return s[:40].rstrip("_")


class VectorStore:
    COLLECTION = "disclosures"

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        persist_dir = persist_dir or settings.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        provider = build_embedding_provider()
        self.model_name = provider.model_name
        # 컬렉션 이름에 임베딩 모델을 붙인다. 모델이 바뀌면 벡터 차원이 달라져 같은 컬렉션에 못 들어간다
        self.collection_name = f"{self.COLLECTION}__{_slug(provider.model_name)}"
        self._chroma = Chroma(collection_name=self.collection_name, embedding_function=provider.get(),
                              persist_directory=persist_dir, collection_metadata={"hnsw:space": "cosine"})

    def add(self, documents: List[Document], ids: List[str]) -> List[str]:
        return self._chroma.add_documents(documents, ids=ids)

    def existing_ids(self, ids: List[str]) -> set:
        if not ids:
            return set()
        got = self._chroma.get(ids=ids, include=[])
        return set(got.get("ids") or [])

    def similarity_search(self, query: str, k: int = 10,
                          where: Optional[Dict[str, Any]] = None) -> List[Tuple[Document, float]]:
        return self._chroma.similarity_search_with_score(query=query, k=k, filter=where)

    def reset(self) -> None:
        self._chroma.reset_collection()
