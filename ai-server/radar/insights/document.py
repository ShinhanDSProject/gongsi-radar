"""기업 상세의 문서 파생 정보(docs/CONTRACT.md §11.1) — 사업 지표(§6.3)·지배구조(§6.4).

기업 상세(CompanyProfile)의 재무 표·시장 지표·공시 목록은 Spring이 Java로 계산하고, 원문(document.xml)을 읽어야
나오는 두 부분만 AI 서버 `GET /ai/insights/{corpCode}`가 만든다. 이 모듈이 그 계산이다.

  사업 지표 — 원문이 있는 최근 사업보고서 두 해(연속)의 표를 비교한다. 표 합계 검산에 재무 API 매출액을 쓴다.
  지배구조 — 최근 사업보고서 재무가 있는 연도(기준일 이전 접수분)와 그 전년의 주요정보를 비교한다.
             재무가 없으면 원문이 있는 최근 사업보고서 연도를 쓴다.
radar/company.py(분리 전 company_profile)에서 그대로 옮겼다 — 결과가 golden(backend/src/test/resources/golden/profile_*.json)의
business·governance·관련 notes와 같아야 한다. 시장 지표·밸류에이션 코드에는 기대지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime

from radar.insights.business import extract_business
from radar.numbers.financials import amount
from radar.insights.governance import build_governance, known_names
from radar.parsing.parser import ParseError, parse_filing_zip
from radar.sources.base import SourceError

try:  # 서비스 소스가 없어도(테스트·CLI) 이 모듈은 돈다
    from radar.sources.service import SourceUnavailable
except ImportError:  # pragma: no cover - httpx 없는 환경
    class SourceUnavailable(SourceError):  # type: ignore[no-redef]
        pass

# 매출액 행 찾기: 표준계정 ID 우선, 없으면 계정명(공백 무시). radar/numbers/valuation.py ACCOUNTS["rev"]와 같은 규칙
_REV_SJ = ("IS", "CIS")
_REV_IDS = ("ifrs-full_Revenue",)
_REV_NAMES = ("매출액", "수익(매출액)", "영업수익")


def _nm(s: str) -> str:
    return "".join((s or "").split())


def revenue_row(rows: list[dict]) -> dict | None:
    cands = [r for r in rows if (r.get("sj_div") or "") in _REV_SJ]
    for r in cands:
        if r.get("account_id") in _REV_IDS:
            return r
    wanted = {_nm(n) for n in _REV_NAMES}
    return next((r for r in cands if _nm(r.get("account_nm")) in wanted), None)


def _as_of(v) -> date:
    if v is None:
        return date.today()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v).replace("-", "")[:8], "%Y%m%d").date()


class _Fin:
    """사업보고서 재무 조회 메모. 같은 연도를 두 번 부르지 않는다."""

    def __init__(self, source, corp_code: str):
        self.source, self.corp = source, corp_code
        self._memo: dict[int, list[dict] | None] = {}

    def rows(self, year: int) -> list[dict] | None:
        if year not in self._memo:
            try:
                self._memo[year] = self.source.financials(self.corp, year, "11011")[0]
            except SourceUnavailable:
                raise
            except SourceError:
                self._memo[year] = None
        return self._memo[year]

    def latest_year(self, as_of: date) -> int | None:
        """기준일 전년부터 4년을 거슬러 올라가며, 기준일 이전에 접수된 사업보고서 재무가 있는 연도."""
        for y in range(as_of.year - 1, as_of.year - 5, -1):
            rows = self.rows(y)
            if not rows:
                continue
            rno = next((r.get("rcept_no") for r in rows if r.get("rcept_no")), None)
            if not rno or rno[:8] <= as_of.strftime("%Y%m%d"):  # 접수번호가 없으면(피어 주요계정) 확인하지 않는다
                return y
        return None

    def revenue(self, year: int) -> int | None:
        rows = self.rows(year)
        r = revenue_row(rows) if rows else None
        return amount(r.get("thstrm_amount")) if r else None


def _doc(source, rcept_no: str):
    return parse_filing_zip(source.document(rcept_no), rcept_no)


def document_insights(source, corp_code: str, as_of=None) -> dict:
    """{business: Business|None, governance: Governance|None, notes: [...]}.

    회사를 찾지 못하면 SourceError. 데이터 서비스 장애(SourceUnavailable)는 notes로 삼키지 않고 올린다 —
    부른 쪽(Spring)이 '데이터 없음'과 '일시 장애'를 구분해야 한다.
    """
    d = _as_of(as_of)
    corps = source.companies()
    c = next((x for x in corps if x["corp_code"] == corp_code), None) or source.resolve(corp_code)
    fin = _Fin(source, c["corp_code"])
    notes: list[str] = []
    try:
        filings = source.filings(c["corp_code"])
    except SourceUnavailable:
        raise
    except SourceError as e:
        filings = []
        notes.append(f"공시 목록 조회 실패: {e}")

    # 사업 지표: 원문이 있는 최근 사업보고서 두 해
    business = None
    annual_docs = sorted([f for f in filings if f["reprt_code"] == "11011" and f["hasDocument"]],
                         key=lambda f: f["bsns_year"], reverse=True)
    if len(annual_docs) >= 2 and annual_docs[0]["bsns_year"] - annual_docs[1]["bsns_year"] == 1:
        cur_f, pr_f = annual_docs[0], annual_docs[1]
        try:
            rev = {f["bsns_year"]: fin.revenue(f["bsns_year"]) for f in (cur_f, pr_f)}
            business = extract_business(_doc(source, pr_f["rcept_no"]), _doc(source, cur_f["rcept_no"]), rev,
                                        (pr_f["bsns_year"], cur_f["bsns_year"]))
        except SourceUnavailable:
            raise
        except (SourceError, ParseError) as e:
            notes.append(f"사업 지표: 원문을 읽지 못함({e})")
    else:
        notes.append("사업 지표: 원문이 있는 연속 두 해 사업보고서가 없어 만들지 않음")

    # 지배구조: 최근 사업보고서 연도와 그 전년
    governance = None
    known = known_names([x for x in corps if x["corp_code"] != c["corp_code"]])
    gyear = fin.latest_year(d) or (annual_docs[0]["bsns_year"] if annual_docs else None)
    if gyear:
        try:
            cur_g = source.governance(c["corp_code"], gyear, "11011")
            try:
                pr_g = source.governance(c["corp_code"], gyear - 1, "11011")
            except SourceUnavailable:
                raise
            except SourceError:
                pr_g = None
            governance = build_governance(cur_g, pr_g, known, c)
        except SourceUnavailable:
            raise
        except SourceError as e:
            notes.append(f"지배구조: {e}")
    return {"business": business, "governance": governance, "notes": notes}
