"""적재 DB를 먼저 보고, 없을 때만 원천을 부르는 소스.

전 종목이 필요한 조회(기업 목록·시세 이력·최근 공시·업종 코드)는 적재 DB가 있으면 그것만 읽는다 — 화면이 원천 API 호출 한도에
묶이지 않는다. 회사 한 곳의 분석(원문·재무)은 적재분이 있으면 쓰고, 없으면 지금처럼 원천을 부른다.

반환 모양은 원천 소스와 같다(OpenDART·공공데이터포털 응답 필드). 그래서 radar의 나머지 코드는 이 래퍼를 모른다.
적재 DB가 비어 있거나 읽을 수 없으면 원천을 그대로 쓴다(수집 전에도 앱이 돈다).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import sqlalchemy as sa

from ..sources import SourceError
from . import tables as T
from .store import IngestStore

logger = logging.getLogger(__name__)


class IngestedSource:
    ingested = True

    def __init__(self, base, engine: sa.Engine):
        self.base = base
        self.store = IngestStore(engine)
        self.engine = engine

    def __getattr__(self, name):                  # resolve·find_report·document·governance·peers·lawsuits·name·calls…
        return getattr(self.base, name)

    @property
    def calls(self) -> int:
        return getattr(self.base, "calls", 0)

    def _rows(self, stmt) -> list:
        try:
            with self.engine.connect() as conn:
                return conn.execute(stmt).mappings().all()
        except sa.exc.SQLAlchemyError as e:
            logger.warning("적재 DB 조회 실패(%s) — 원천을 씁니다", type(e).__name__)
            return []

    # ---- 기업 ------------------------------------------------------------------------------
    def companies(self) -> list[dict]:
        rows = self._rows(sa.select(T.company).where(T.company.c.listed & T.company.c.stock_code.is_not(None)))
        if not rows:
            return self.base.companies()
        induty = {c["corp_code"]: c.get("induty") for c in self._base_companies()}
        return [{"corp_code": r["corp_code"], "corp_name": r["corp_name"], "stock_code": r["stock_code"],
                 "induty": induty.get(r["corp_code"]), "induty_code": r["induty_code"], "market": r["market"]}
                for r in rows]

    def _base_companies(self) -> list[dict]:
        # 업종 '설명'(샘플의 '2차전지 소재' 같은 표시용 문구)은 적재 대상이 아니다. 샘플일 때만 원천에서 붙인다
        return self.base.companies() if getattr(self.base, "name", "") == "sample" else []

    def induty_code(self, corp_code: str) -> str | None:
        rows = self._rows(sa.select(T.company.c.induty_code).where(T.company.c.corp_code == corp_code))
        if rows and rows[0]["induty_code"]:
            return rows[0]["induty_code"]
        return self.base.induty_code(corp_code)

    def new_listings(self, days: int = 30) -> list[dict]:
        """최근 처음 확인한 기업. 첫 적재일(전 종목을 처음 넣은 날)에 들어온 회사는 '신규'가 아니다."""
        rows = self._rows(sa.select(sa.func.min(T.company.c.first_seen).label("d")))
        if not rows or rows[0]["d"] is None:
            return []
        first_load = rows[0]["d"]
        since = date.today() - timedelta(days=days)
        rows = self._rows(sa.select(T.company).where((T.company.c.first_seen > first_load)
                                                     & (T.company.c.first_seen >= since))
                          .order_by(T.company.c.first_seen.desc()))
        return [dict(r) for r in rows]

    # ---- 시세·지수 ---------------------------------------------------------------------------
    @staticmethod
    def _price_row(r) -> dict:
        s = lambda v: None if v is None else str(v)                            # noqa: E731 원천 응답처럼 문자열로
        return {"basDt": r["bas_dt"], "srtnCd": r["stock_code"], "itmsNm": r["itms_nm"], "mrktCtg": r["mrkt_ctg"],
                "clpr": s(r["clpr"]), "lstgStCnt": s(r["lstg_st_cnt"]), "mrktTotAmt": s(r["mrkt_tot_amt"])}

    def market_history(self) -> dict[str, list[dict]]:
        rows = self._rows(sa.select(T.market_daily))
        if not rows:
            return self.base.market_history()
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["stock_code"], []).append(self._price_row(r))
        return out

    def market(self, stock_code: str) -> list[dict]:
        rows = self._rows(sa.select(T.market_daily).where(T.market_daily.c.stock_code == stock_code)
                          .order_by(T.market_daily.c.bas_dt.desc()))
        return [self._price_row(r) for r in rows] if rows else self.base.market(stock_code)

    def index_series(self, name: str) -> list[dict]:
        rows = self._rows(sa.select(T.index_daily).where(T.index_daily.c.idx_nm == name).order_by(T.index_daily.c.bas_dt))
        if not rows:
            return self.base.index_series(name)
        return [{"basDt": r["bas_dt"], "idxNm": name, "clpr": str(r["clpr"])} for r in rows]

    # ---- 공시·재무 ---------------------------------------------------------------------------
    def recent_filings(self, days: int = 90, limit: int = 200) -> list[dict]:
        """최신 접수순. 기간으로 자르지 않는다 — 원천 소스와 같은 결과를 내야 화면이 수집 전후로 달라지지 않는다."""
        rows = self._rows(sa.select(T.filing).order_by(T.filing.c.rcept_dt.desc(), T.filing.c.rcept_no.desc())
                          .limit(limit))
        if not rows:
            return self.base.recent_filings()
        doc_cached = getattr(self.base, "name", "") == "opendart"
        return [{"rcept_no": r["rcept_no"], "corp_code": r["corp_code"], "corp_name": r["corp_name"],
                 "stock_code": r["stock_code"], "report_nm": r["report_nm"], "rcept_dt": r["rcept_dt"],
                 "rm": r["rm"], "reprt_code": r["reprt_code"], "bsns_year": r["bsns_year"],
                 # OpenDART는 원문을 언제든 받을 수 있다. 샘플은 실제로 보유한 것만
                 "hasDocument": bool(r["has_document"]) or doc_cached} for r in rows]

    def financials(self, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[list[dict], str]:
        rows = self._rows(sa.select(T.financial_line).where(
            (T.financial_line.c.corp_code == corp_code) & (T.financial_line.c.bsns_year == int(bsns_year))
            & (T.financial_line.c.reprt_code == str(reprt_code))).order_by(T.financial_line.c.ord))
        for fs in ("CFS", "OFS"):
            lines = [r for r in rows if r["fs_div"] == fs]
            if lines:
                return [{"rcept_no": r["rcept_no"], "reprt_code": reprt_code, "bsns_year": str(bsns_year),
                         "corp_code": corp_code, "sj_div": r["sj_div"] or None, "account_id": r["account_id"],
                         "account_nm": r["account_nm"], "ord": str(r["ord"]), "fs_div": fs,
                         **{c: r[c] for c in T.FIN_FIELDS if r[c] is not None}} for r in lines], fs
        return self.base.financials(corp_code, bsns_year, reprt_code)


def wrap(source, url: str | None):
    """RADAR_INGEST_DB가 있고 적재가 한 번이라도 돌았으면 감싼다. 아니면 원천 그대로."""
    if not url:
        return source
    try:
        engine = sa.create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3} if url.startswith("mysql") else {})
        if IngestStore(engine).has_data():
            return IngestedSource(source, engine)
    except (sa.exc.SQLAlchemyError, ImportError, SourceError) as e:
        logger.warning("적재 DB를 쓰지 않습니다: %s", e)
    return source
