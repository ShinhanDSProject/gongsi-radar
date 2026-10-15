"""공시·재무·지배구조·시장 Tool. 모두 조회(Read)다.

데이터는 radar 소스로 받는다. AI 서버에서는 RADAR_SOURCE=service — Spring 내부 데이터 API(docs/CONTRACT.md §11.2)이고
원천 키는 이 서버에 없다. 시장 지표(get_valuation)는 Spring이 준 원천 재무·시세로 radar가 계산한다.

Tool 인자는 LLM이 채울 수 있는 값(회사·연도·보고서)만 받는다. 어느 분석(job) 안에서 불렸는지는
contextvar로 알고, 같은 분석의 Worker들은 radar 세션 하나를 나눠 쓴다(services/radar_session.py).

돌려주는 값은 요약이다. Agent 컨텍스트를 아끼고, 인용 ID(문단 pid)를 그대로 실어 근거를 따라갈 수 있게 한다.
리포트 본문(RadarReport)은 Tool 결과가 아니라 세션에서 직접 만든다 — Tool 요약을 이어 붙여 리포트를 만들면
요약 과정에서 숫자가 바뀔 수 있다. 숫자는 코드가 계산한 원본에서만 나온다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from radar.config import Settings as RadarSettings
from radar.sources import make_source

from ..services.radar_session import sessions

logger = logging.getLogger(__name__)


def _source():
    return make_source(RadarSettings())


def _filing_brief(f: dict) -> dict:
    return {"rceptNo": f.get("rcept_no"), "reportNm": f.get("report_nm"), "rceptDt": f.get("rcept_dt"),
            "url": f.get("url")}


# ---- 기업 상세의 원문 파생 정보 --------------------------------------------------------------
def get_document_insights(corp_code: str) -> Dict[str, Any]:
    """사업 지표·지배구조(원문을 읽어야 나오는 부분). Spring 기업 상세가 business·governance 칸을 채우려고 부른다."""
    from radar.insights import document_insights
    return document_insights(_source(), str(corp_code).strip())


# ---- 분석 세션 기반 ----------------------------------------------------------------------
def compare_filings(company: str, bsns_year: int, reprt_code: str = "11011") -> Dict[str, Any]:
    """전년 같은 보고서와 당기 보고서를 비교한다(수집·파싱 → 수치 → 본문 비교)."""
    sess = sessions.for_tool(company, bsns_year, reprt_code)
    sess.prepare()
    st = sess.state
    changes = st.get("changes") or []
    by_type: Dict[str, int] = {}
    by_topic: Dict[str, int] = {}
    for c in changes:
        by_type[c["edit_type"]] = by_type.get(c["edit_type"], 0) + 1
        by_topic[c["topic"]] = by_topic.get(c["topic"], 0) + 1
    _index_for_rag(sess)
    return {
        "company": st["company"].get("corp_name"), "corpCode": st["company"].get("corp_code"),
        "prior": _filing_brief(st["filings"]["prior"]), "current": _filing_brief(st["filings"]["current"]),
        "changesByType": by_type, "changesByTopic": by_topic, "tables": len(st.get("tables") or []),
        "injectionSuspected": [c["id"] for c in changes if "지시문 의심" in c.get("flags", [])],
        "topChanges": [{"id": c["id"], "editType": c["edit_type"], "topic": c["topic"], "summary": c["summary"],
                        "sectionPath": c["section_path"], "citation": f"[{(c['new'] or c['old'])[0]['pid']}]"}
                       # [보안] 지시문 의심 문단은 근거(인용)로 내보내지 않는다. id만 injectionSuspected에 싣는다
                       for c in changes if (c["new"] or c["old"]) and "지시문 의심" not in c.get("flags", [])][:8],
    }


def get_financial_changes(company: str, bsns_year: int, reprt_code: str = "11011") -> Dict[str, Any]:
    """계정 증감(코드 계산)과 관련 서술 연결 결과. 관련 서술 연결은 Financial Analyst Worker가 돌린다."""
    sess = sessions.for_tool(company, bsns_year, reprt_code)
    sess.prepare()
    st = sess.state
    accts = st.get("accounts") or []
    rels = st.get("relations") or {}
    return {
        "fsDiv": st.get("fs_div"),
        "flagged": [{"account": a["account_nm"], "prior": a["prior"], "current": a["current"], "yoyPct": a["yoy_pct"],
                     "flags": a["flags"]} for a in accts if a["flags"] or a["is_key"]],
        "relations": [{"account": r["account_nm"], "level": r["level"], "statement": r["statement"],
                       "citations": [f"[{e['pid']}]" for e in r.get("evidence", [])],
                       "verification": (r.get("verification") or {}).get("status")}
                      for r in rels.values()],
    }


def get_business_metrics(company: str, bsns_year: int, reprt_code: str = "11011") -> Dict[str, Any]:
    """사업 지표(부문 매출·수주·생산능력·가동률). 검산을 통과한 행만 숫자로 싣고 나머지는 사유만 싣는다."""
    sess = sessions.for_tool(company, bsns_year, reprt_code)
    sess.prepare()
    biz = sess.state.get("business") or {}
    out = []
    for g in biz.get("groups", []):
        rows = []
        for r in g.get("rows", []):
            if r.get("status") == "검산 통과":
                rows.append({"label": r["label"], "values": r.get("values", [])})
            else:
                rows.append({"label": r["label"], "status": r.get("status")})
        out.append({"kind": g.get("kind"), "unit": g.get("unit"), "citation": f"[{g.get('currentPid')}]",
                    "rows": rows})
    return {"groups": out, "summary": biz.get("summary"), "note": biz.get("note")}


def get_governance(company: str, bsns_year: int, reprt_code: str = "11011") -> Dict[str, Any]:
    sess = sessions.for_tool(company, bsns_year, reprt_code)
    sess.prepare()
    gov = sess.state.get("governance") or {}
    return {"changes": gov.get("changes", []), "rceptNo": gov.get("rceptNo"),
            "citation": f"[dart:{gov.get('rceptNo')}]" if gov.get("rceptNo") else None}


def get_lawsuits(company: str, bsns_year: int, reprt_code: str = "11011") -> List[Dict[str, Any]]:
    """주요사항보고서(소송 등 제기)."""
    sess = sessions.for_tool(company, bsns_year, reprt_code)
    sess.prepare()
    return [{"title": r.get("icnm"), "plaintiff": r.get("ac_ap"), "claim": r.get("rq_cn"), "court": r.get("cpct"),
             "date": r.get("lgd"), "citation": f"[dart:{r.get('rcept_no')}]"} for r in sess.state.get("lawsuits") or []]


def get_valuation(company: str) -> Dict[str, Any]:
    """TTM·PER·PBR(계산식·출처 포함). 판단 문구는 만들지 않는다. 원자료(재무·시세)는 소스(Spring)에서 받는다."""
    from radar.valuation import compute_valuation
    src = _source()
    return compute_valuation(src, src.resolve(str(company)))


def get_stock_price(stock_code: str, days: int = 5) -> List[Dict[str, Any]]:
    src = _source()
    comp = src.resolve(str(stock_code))
    rows = src.market(comp["stock_code"]) or []
    rows = sorted(rows, key=lambda r: r.get("basDt", ""))[-min(max(int(days), 1), 60):]
    return [{"date": r.get("basDt"), "close": r.get("clpr"), "marketCap": r.get("mrktTotAmt"),
             "citation": f"[market-data:{comp['stock_code']}]"} for r in rows]


def search_disclosures(query: str, top_k: int = 5, corp_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """공시 원문 문단 검색. 지시문 의심 문단(LOW)은 결과에 나오지 않는다."""
    from ..rag.service import get_rag_service
    hits = get_rag_service().search(query, ["RAG_READ"], top_k=min(max(int(top_k), 1), 10), corp_code=corp_code)
    return [{"citation": f"[{h.chunk_id}]", "section": h.section_path, "score": round(h.score, 2),
             "trust": h.trust_level, "content": h.content[:200]} for h in hits]


def get_publication_history(corp_code: str) -> List[Dict[str, Any]]:
    """Core Zone 발행 원장 조회(조회 키). 쓰기 메서드는 이 서버에 없다."""
    from .core_client import core_client
    return [{"publicationId": p.get("publicationId"), "periodLabel": p.get("periodLabel"), "version": p.get("version"),
             "status": p.get("status"), "decidedAt": p.get("decidedAt")}
            for p in core_client.list_publications(corp_code)]


# ---- RAG 색인 ----------------------------------------------------------------------------
def _index_for_rag(sess) -> None:
    """비교한 두 문서를 RAG에 넣는다. 색인 실패는 분석을 막지 않는다(검색 근거만 줄어든다)."""
    if getattr(sess, "_indexed", False):
        return
    try:
        from ..rag.indexer import index_document
        from ..rag.service import get_rag_service
        st = sess.state
        store = get_rag_service().store
        for side in ("prior", "current"):
            f = st["filings"][side]
            index_document(store, st["docs"][side], corp_code=st["company"]["corp_code"],
                           corp_name=st["company"]["corp_name"], report_nm=f["report_nm"], rcept_dt=f.get("rcept_dt"))
        sess._indexed = True
    except Exception as e:
        logger.warning("RAG 색인 실패(%s: %s)", type(e).__name__, e)
