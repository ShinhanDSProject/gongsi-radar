"""RAG 검색 서비스 — Scope 검사·신뢰도 필터·무결성 해시 검증."""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_TRUST = ["HIGH", "MEDIUM"]      # [보안] LOW(지시문 의심)는 근거로 쓰지 않는다


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    title: str
    source: str
    published_at: str
    content: str
    score: float
    trust_level: str
    section_path: str


class RAGService:
    def __init__(self, store: Optional[VectorStore] = None) -> None:
        self.store = store or VectorStore()

    def search(self, query: str, scope: List[str], *, top_k: int = 5, min_score: float = 0.3,
               trust_levels: Optional[List[str]] = None, corp_code: Optional[str] = None,
               rcept_no: Optional[str] = None) -> List[SearchHit]:
        if "RAG_READ" not in scope:
            raise PermissionError("RAG_READ scope required")
        conds: List[Dict[str, Any]] = [{"trust_level": {"$in": trust_levels or DEFAULT_TRUST}}]
        if corp_code:
            conds.append({"corp_code": corp_code})
        if rcept_no:
            conds.append({"rcept_no": rcept_no})
        where = conds[0] if len(conds) == 1 else {"$and": conds}
        hits: List[SearchHit] = []
        for doc, distance in self.store.similarity_search(query, k=top_k * 3, where=where):
            score = max(0.0, 1.0 - distance)           # cosine distance → similarity
            if score < min_score:
                continue
            if not self._verify_hash(doc):              # 색인 후 내용이 바뀐 청크는 근거로 쓰지 않는다
                logger.warning("integrity check failed: %s", doc.metadata.get("chunk_id"))
                continue
            m = doc.metadata
            hits.append(SearchHit(m.get("chunk_id", ""), m.get("doc_id", ""), m.get("title", ""), m.get("source", ""),
                                  m.get("published_at", ""), doc.page_content, round(score, 4),
                                  m.get("trust_level", "MEDIUM"), m.get("section_path", "")))
            if len(hits) >= top_k:
                break
        return hits

    @staticmethod
    def _verify_hash(doc) -> bool:
        stored = doc.metadata.get("content_hash")
        return not stored or stored == hashlib.sha256(doc.page_content.encode("utf-8")).hexdigest()


_service: Optional[RAGService] = None
_lock = threading.Lock()


def get_rag_service() -> RAGService:
    """임베딩 모델 로딩 비용이 크므로 프로세스당 한 번만 만든다(LangChain이 sync Tool을 스레드풀에서 돌려 락이 필요)."""
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                _service = RAGService()
    return _service
