"""앱 시작 시 Tool을 Gateway에 등록한다. 전부 조회다 — 발행·승인 Tool은 없다."""
from __future__ import annotations

import json

from . import compliance as cp
from . import disclosure_tools as dt
from .gateway import ToolSpec, gateway


def _brief(v) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= 200 else s[:200] + "..."


TOOLS = [
    ("search_companies", dt.search_companies, ["DISCLOSURE_READ"], "회사명·종목코드·고유번호로 기업을 찾는다"),
    ("get_company_profile", dt.get_company_profile, ["DISCLOSURE_READ"], "기업 상세(재무·사업 지표·지배구조·공시 목록)"),
    ("compare_filings", dt.compare_filings, ["DISCLOSURE_READ"], "전년 대비 정기보고서 본문 비교"),
    ("get_financial_changes", dt.get_financial_changes, ["DISCLOSURE_READ"], "계정 증감과 관련 서술 연결 결과"),
    ("get_business_metrics", dt.get_business_metrics, ["DISCLOSURE_READ"], "부문 매출·수주·생산능력·가동률(검산 통과분)"),
    ("get_governance", dt.get_governance, ["DISCLOSURE_READ"], "주주·임원·타법인출자 변동"),
    ("get_lawsuits", dt.get_lawsuits, ["DISCLOSURE_READ"], "주요사항보고서(소송 등 제기)"),
    ("get_valuation", dt.get_valuation, ["MARKET_DATA_READ"], "TTM·PER·PBR(계산식·출처 포함)"),
    ("get_stock_price", dt.get_stock_price, ["MARKET_DATA_READ"], "최근 N영업일 종가·시가총액"),
    ("get_market_overview", dt.get_market_overview, ["MARKET_DATA_READ"], "시장 화면(지수·시가총액 추이·업종 지도·최근 공시)"),
    ("search_disclosures", dt.search_disclosures, ["RAG_READ"], "공시 원문 문단 검색(RAG)"),
    ("check_compliance_rules", cp.check_compliance_rules, ["REPORT_READ"], "리포트 초안의 규정 위반 후보 검사"),
    ("get_publication_history", dt.get_publication_history, ["PUBLICATION_READ"], "발행 원장 이력 조회(Core Zone)"),
]


def register_default_tools() -> None:
    for name, func, scopes, desc in TOOLS:
        if not gateway.is_registered(name):
            gateway.register(ToolSpec(name=name, func=func, required_scopes=scopes, description=desc, summarize=_brief))
