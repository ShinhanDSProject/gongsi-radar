"""데이터 소스. 분석 파이프라인(radar)이 데이터를 받는 유일한 창구다.

[역할 분리, docs/CONTRACT.md §11] OpenDART·공공데이터포털 연동과 일일 수집은 Spring(backend)이 맡는다.
AI 서버는 원천 키를 갖지 않고 ServiceSource(radar/service_source.py, RADAR_SOURCE=service)로 Spring 내부 데이터 API만 부른다.
SampleSource는 같은 응답 모양의 가상 샘플(저장소 루트 samples/data)을 읽는다 — 테스트와 CLI 단독 실행용.

공통 인터페이스(응답 모양은 원천 그대로)
  resolve(query) · find_report(corp, year, reprt) · document(rcept_no) · financials(corp, year, reprt) → (rows, fs_div)
  peers(corp, year, reprt) · lawsuits(corp, bgn, end) · companies() · filings(corp)
  governance(corp, year, reprt) → {shareholders, executives, investments, rcept_no}
  market(stock_code) → [getStockPriceInfo item, ...]  최신일 먼저
"""
from __future__ import annotations

import json
import re
from pathlib import Path


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


def _filing_row(r: dict, has_doc: bool) -> dict | None:
    code, year = report_kind(r.get("report_nm", ""))
    if not code:
        return None
    return {"rcept_no": r["rcept_no"], "report_nm": r["report_nm"], "rcept_dt": r["rcept_dt"],
            "reprt_code": code, "bsns_year": year, "hasDocument": has_doc}


def _rows(d: dict) -> list[dict]:
    return d.get("list", []) if d.get("status") == "000" else []


def _gov(sh: list[dict], ex: list[dict], inv: list[dict]) -> dict:
    rno = next((r.get("rcept_no") for r in sh + ex + inv if r.get("rcept_no")), None)
    return {"shareholders": sh, "executives": ex, "investments": inv, "rcept_no": rno}


class SampleSource:
    name = "sample"

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        if not (self.dir / "list.json").exists():
            raise SourceError(f"샘플 데이터가 없습니다: {self.dir} (저장소 루트에서 python samples/build_samples.py 실행)")
        self.calls = 0

    def _json(self, name: str) -> dict:
        self.calls += 1
        p = self.dir / name
        if not p.exists():
            return {"status": "013", "message": "조회된 데이타가 없습니다.", "list": []}
        return json.loads(p.read_text(encoding="utf-8"))

    def resolve(self, query: str) -> dict:
        corps = json.loads((self.dir / "corp_codes.json").read_text(encoding="utf-8"))
        for c in corps:
            if query in (c["corp_code"], c["stock_code"], c["corp_name"]):
                return c
        raise SourceError(f"샘플에 없는 회사입니다: {query} (가능: {[c['stock_code'] for c in corps]})")

    def find_report(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        tag = f"({bsns_year}.{REPRT[reprt_code]['mm']})"
        for r in self._json("list.json")["list"]:
            if r["corp_code"] == corp_code and tag in r["report_nm"] and REPRT[reprt_code]["name"] in r["report_nm"]:
                return {**r, "bsns_year": bsns_year, "reprt_code": reprt_code, "url": dart_url(r["rcept_no"])}
        raise SourceError(f"{bsns_year}년 {REPRT[reprt_code]['name']}를 찾지 못했습니다.")

    def document(self, rcept_no: str) -> bytes:
        self.calls += 1
        p = self.dir / "filings" / f"{rcept_no}.zip"
        if not p.exists():
            raise SourceError(f"원문 ZIP 없음: {p}")
        return p.read_bytes()

    def financials(self, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[list[dict], str]:
        for fs in ("CFS", "OFS"):
            d = self._json(f"fnltt_{corp_code}_{bsns_year}_{reprt_code}_{fs}.json")
            if d.get("status") == "000" and d.get("list"):
                return d["list"], fs
        # 피어: 단일회사 전체 재무 파일이 없으면 다중회사 주요계정(피어 파일)의 그 회사 행으로 대신한다
        rows = [r for r in self._json(f"peers_{bsns_year}_{reprt_code}.json").get("list", [])
                if r.get("corp_code") == corp_code]
        if rows:
            return rows, rows[0].get("fs_div", "CFS")
        raise SourceError("재무제표 데이터가 없습니다(013).")

    def peers(self, corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
        return self._json(f"peers_{bsns_year}_{reprt_code}.json").get("list", [])

    def lawsuits(self, corp_code: str, bgn: str, end: str) -> list[dict]:
        rows = self._json(f"lwstLg_{corp_code}.json").get("list", [])
        return [r for r in rows if bgn <= r.get("lgd", "").replace("-", "") <= end]

    def companies(self) -> list[dict]:
        corps = json.loads((self.dir / "corp_codes.json").read_text(encoding="utf-8"))
        return [{"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c.get("stock_code", ""),
                 "induty": c.get("induty"), "induty_code": c.get("induty_code"), "market": c.get("market")}
                for c in corps if c.get("stock_code")]

    def filings(self, corp_code: str) -> list[dict]:
        out = []
        for r in self._json("list.json")["list"]:
            if r["corp_code"] != corp_code:
                continue
            row = _filing_row(r, (self.dir / "filings" / f"{r['rcept_no']}.zip").exists())
            if row:
                out.append(row)
        return sorted(out, key=lambda x: x["rcept_dt"], reverse=True)

    def governance(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        tail = f"{corp_code}_{bsns_year}_{reprt_code}.json"
        g = _gov(*(_rows(self._json(f"{n}_{tail}")) for n in ("hyslrSttus", "exctvSttus", "otrCprInvstmntSttus")))
        if not (g["shareholders"] or g["executives"] or g["investments"]):
            raise SourceError(f"{bsns_year}년 지배구조 데이터가 없습니다(013).")
        return g

    def market(self, stock_code: str) -> list[dict]:
        p = self.dir / f"market_{stock_code}.json"
        if not p.exists():
            return []
        self.calls += 1
        return _price_items(json.loads(p.read_text(encoding="utf-8")))



def _price_items(d: dict) -> list[dict]:
    """getStockPriceInfo 응답 → item 목록. 한 건이면 dict로 온다."""
    body = (d.get("response") or {}).get("body") or {}
    item = (body.get("items") or {}).get("item") or []
    return [item] if isinstance(item, dict) else list(item)


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
        from .service_source import ServiceSource
        return ServiceSource(settings.service_url, settings.service_key, timeout=settings.service_timeout)
    if settings.source == "sample":
        return SampleSource(settings.sample_dir)
    raise SourceError(f"RADAR_SOURCE={settings.source}는 지원하지 않습니다(service | sample). "
                      "OpenDART 연동은 Spring(backend)이 맡는다 — docs/CONTRACT.md §11")
