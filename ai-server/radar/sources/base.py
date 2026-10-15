"""데이터 소스. 분석 파이프라인(radar)이 데이터를 받는 유일한 창구다.

[역할 분리, docs/CONTRACT.md §11] OpenDART·공공데이터포털 연동과 일일 수집은 Spring(backend)이 맡는다.
AI 서버는 원천 키를 갖지 않고 ServiceSource(radar/sources/service.py, RADAR_SOURCE=service)로 Spring 내부 데이터 API만 부른다.
SampleSource는 같은 응답 모양의 가상 샘플(저장소 루트 samples/data)을 읽는다 — 테스트와 CLI 단독 실행용.

공통 인터페이스(응답 모양은 원천 그대로)
  resolve(query) · find_report(corp, year, reprt) · document(rcept_no) · financials(corp, year, reprt) → (rows, fs_div)
  peers(corp, year, reprt) · lawsuits(corp, bgn, end) · companies() · filings(corp)
  governance(corp, year, reprt) → {shareholders, executives, investments, rcept_no}
  market(stock_code) → [getStockPriceInfo item, ...]  최신일 먼저
"""
from __future__ import annotations

import re


REPRT = {
    "11011": {"name": "사업보고서", "detail": "A001", "mm": "12"},
    "11012": {"name": "반기보고서", "detail": "A002", "mm": "06"},
    "11013": {"name": "1분기보고서", "detail": "A003", "mm": "03"},
    "11014": {"name": "3분기보고서", "detail": "A003", "mm": "09"},
}


class SourceError(RuntimeError):
    pass


def dart_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


_RNM = re.compile(r"\((\d{4})\.(\d{2})\)")


def report_kind(report_nm: str) -> tuple[str | None, int | None]:
    """'반기보고서 (2026.06)' → ('11012', 2026). 정기보고서가 아니면 (None, None)."""
    m = _RNM.search(report_nm or "")
    if not m:
        return None, None
    for code, info in REPRT.items():
        if info["name"] in report_nm and info["mm"] == m.group(2):
            return code, int(m.group(1))
    return None, None


def data_origin(source) -> str:
    """데이터가 실제로 어디서 왔는가(sample·opendart). 서비스 소스는 Spring이 응답 헤더로 알려 준 값을 쓴다."""
    return getattr(source, "origin", None) or getattr(source, "name", "")


def make_source(settings):
    """데이터 소스를 만든다.

    service — Spring 내부 데이터 API(AI 서버의 기본, docs/CONTRACT.md §11.2). OpenDART·공공데이터포털 연동, 일일 수집,
              적재 DB는 모두 Spring 몫이다. 이 서버는 원천 키를 갖지 않는다.
    sample  — 저장소 루트 samples/data(테스트·CLI 단독 실행)
    """
    if settings.source == "service":
        from radar.sources.service import ServiceSource
        return ServiceSource(settings.service_url, settings.service_key, timeout=settings.service_timeout)
    if settings.source == "sample":
        from radar.sources.sample import SampleSource
        return SampleSource(settings.sample_dir)
    raise SourceError(f"RADAR_SOURCE={settings.source}는 지원하지 않습니다(service | sample). "
                      "OpenDART 연동은 Spring(backend)이 맡는다 — docs/CONTRACT.md §11")
