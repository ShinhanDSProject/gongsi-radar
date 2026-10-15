"""공시 원문 문단을 RAG에 넣는다. 청크 = radar 파서가 나눈 문단 하나(인용 ID가 곧 chunk_id).

신뢰도(trust_level):
  HIGH   : DART 원문 문단
  MEDIUM : 원문 안에서 외부 추정치를 인용한 문단("외부 조사기관", "추정치" 등)
  LOW    : 지시문 의심 문단(간접 프롬프트 인젝션). 검색 기본값(HIGH·MEDIUM)에서 빠진다 — RAG Poisoning 방어

문서를 쪼개는 기준을 새로 만들지 않는 이유: 인용 ID가 같아야 리포트의 근거와 검색 결과가 같은 문단을 가리킨다.
메타는 MariaDB(disclosure_document·disclosure_chunk)에도 남긴다. 벡터는 Chroma에만 있다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from typing import Dict, List, Optional

import sqlalchemy as sa
from langchain_core.documents import Document

from radar.diff.classify import injection_suspected
from radar.parsing.parser import ParsedDoc

from ..infra.db import get_engine

logger = logging.getLogger(__name__)

_EXTERNAL_RE = re.compile(r"외부\s*조사기관|추정치|시장조사|리서치\s*기관")


def trust_of(text: str) -> str:
    if injection_suspected(text):
        return "LOW"
    if _EXTERNAL_RE.search(text):
        return "MEDIUM"
    return "HIGH"


def _published(rcept_dt: Optional[str]) -> str:
    if rcept_dt and len(rcept_dt) == 8:
        return date(int(rcept_dt[:4]), int(rcept_dt[4:6]), int(rcept_dt[6:])).isoformat()
    return ""


def build_chunks(doc: ParsedDoc, *, corp_code: str, corp_name: str, report_nm: str,
                 rcept_dt: Optional[str]) -> List[Document]:
    doc_id = f"dart:{doc.rcept_no}"
    out = []
    for i, b in enumerate(doc.paragraphs()):
        out.append(Document(page_content=b.text, metadata={
            "chunk_id": b.id, "doc_id": doc_id, "chunk_index": i, "corp_code": corp_code, "rcept_no": doc.rcept_no,
            "title": f"{corp_name} {report_nm}", "source": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={doc.rcept_no}",
            "published_at": _published(rcept_dt), "section_path": b.section_path, "trust_level": trust_of(b.text),
            "content_hash": hashlib.sha256(b.text.encode("utf-8")).hexdigest(),
        }))
    return out


def index_document(store, doc: ParsedDoc, *, corp_code: str, corp_name: str, report_nm: str,
                   rcept_dt: Optional[str]) -> Dict[str, int]:
    """이미 들어간 청크는 건너뛴다(인용 ID가 내용 해시를 품고 있어 같은 ID = 같은 문단)."""
    chunks = build_chunks(doc, corp_code=corp_code, corp_name=corp_name, report_nm=report_nm, rcept_dt=rcept_dt)
    ids = [c.metadata["chunk_id"] for c in chunks]
    have = store.existing_ids(ids)
    new = [c for c in chunks if c.metadata["chunk_id"] not in have]
    if new:
        store.add(new, ids=[c.metadata["chunk_id"] for c in new])
        _save_meta(doc, new, corp_code=corp_code, title=f"{corp_name} {report_nm}", rcept_dt=rcept_dt,
                   model=store.model_name)
    low = sum(1 for c in chunks if c.metadata["trust_level"] == "LOW")
    return {"chunks": len(chunks), "added": len(new), "isolated": low}


def _save_meta(doc: ParsedDoc, chunks: List[Document], *, corp_code: str, title: str, rcept_dt: Optional[str],
               model: str) -> None:
    """MariaDB 메타 기록. 실패해도 색인은 유지한다(검색은 Chroma만으로 돈다)."""
    try:
        with get_engine().begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO disclosure_document (doc_id, corp_code, rcept_no, title, doc_type, source, published_at,
                                                 trust_level, content_hash, meta_json)
                VALUES (:doc_id, :corp, :rno, :title, 'periodic_report', :src, :pub, 'HIGH', :hash, :meta)
                ON DUPLICATE KEY UPDATE title = VALUES(title)
            """), {"doc_id": f"dart:{doc.rcept_no}", "corp": corp_code, "rno": doc.rcept_no, "title": title,
                   "src": chunks[0].metadata["source"], "pub": _published(rcept_dt) or None,
                   "hash": hashlib.sha256("".join(c.page_content for c in chunks).encode()).hexdigest(),
                   "meta": json.dumps({"chosen_file": doc.chosen_file, "encoding": doc.encoding_used},
                                      ensure_ascii=False)})
            for c in chunks:
                m = c.metadata
                conn.execute(sa.text("""
                    INSERT IGNORE INTO disclosure_chunk (doc_id, chunk_id, chunk_index, section_path, content,
                                                         trust_level, injection_flag, embedding_model, vector_id)
                    VALUES (:doc_id, :cid, :idx, :sp, :content, :trust, :inj, :model, :cid)
                """), {"doc_id": m["doc_id"], "cid": m["chunk_id"], "idx": m["chunk_index"],
                       "sp": m["section_path"][:500], "content": c.page_content, "trust": m["trust_level"],
                       "inj": m["trust_level"] == "LOW", "model": model})
    except Exception as e:
        logger.warning("RAG 메타 기록 실패(%s: %s). 벡터 색인은 유지한다", type(e).__name__, e)
