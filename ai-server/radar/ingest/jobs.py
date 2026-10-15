"""일일 수집 작업. 원천(OpenDART·공공데이터포털)에서 받아 적재 DB에 upsert한다.

단계와 우선순위(호출 예산이 모자라면 뒤 단계부터 다음 날로 밀린다):
  1 companies  상장사 목록(corpCode.xml)        — 신규 상장·상장폐지 표시
  2 filings    최근 정기공시(list.json)         — 증분. backfill은 회사별 3년치
  3 market     시세(날짜별 전 종목)             — 저장된 마지막 날짜 이후만
  4 index      지수 일별 종가
  5 financials 새로 접수된 보고서의 재무       — 같은 접수번호는 다시 부르지 않는다
  6 induty     업종 코드(기업개황)              — 시가총액 큰 회사부터, 확인한 지 90일 지난 것만
  7 documents  원문 ZIP                         — 최근 정기공시만(디스크 캐시에 보관)

원칙
  - 멱등: 모든 쓰기는 upsert. 같은 날 두 번 돌려도 결과가 같다
  - 이어 하기: 예산이 떨어지면 그 단계는 PARTIAL로 남기고 남은 대상 수를 기록한다. 다음 실행이 같은 조건으로 다시 고르면
    아직 안 한 것부터 잡힌다(완료 표시가 DB에 있으므로)
  - 호출 수는 source.calls 증가분으로 센다. 캐시 적중은 호출이 아니다
  - Kill Switch가 켜져 있으면 시작하지 않고, 단계 사이와 단위 50개마다 다시 확인한다
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import sqlalchemy as sa

from ..sources import SourceError, report_kind
from . import tables as T
from .store import IngestStore

logger = logging.getLogger(__name__)

STEPS = ("companies", "filings", "market", "index", "financials", "induty", "documents")
INDEX_NAMES = ("코스피", "코스닥")
INDUTY_RECHECK_DAYS = 90
FINANCIAL_GIVE_UP_DAYS = 30        # 접수 후 이 기간이 지나도 재무가 없으면(013) 더 부르지 않는다


class BudgetExhausted(Exception):
    pass


class KillSwitchOn(Exception):
    pass


class Budget:
    """원천 호출 예산. 실행을 시작한 뒤 source.calls(실제 API 호출 수)가 늘어난 만큼을 실시간으로 뺀다.
    단계가 끝날 때 더하면 한 단계 안에서 예산을 넘겨도 막지 못한다 — 재무 단계 하나가 하루 한도를 다 쓸 수 있다."""

    def __init__(self, limit: int, counter: Callable[[], int]):
        self.limit, self._counter = limit, counter
        self._start = counter()

    @property
    def used(self) -> int:
        return self._counter() - self._start

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)

    def check(self) -> None:
        if self.left <= 0:
            raise BudgetExhausted()


@dataclass
class StepResult:
    step: str
    status: str = "DONE"
    calls: int = 0
    rows: int = 0
    remaining: int = 0
    error: str | None = None


@dataclass
class RunReport:
    run_uid: str
    mode: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return sum(s.calls for s in self.steps)

    def summary(self) -> str:
        return " · ".join(f"{s.step} {s.status}(호출 {s.calls}, 행 {s.rows}"
                          + (f", 남음 {s.remaining}" if s.remaining else "") + ")" for s in self.steps)


class Ingestor:
    def __init__(self, source, store: IngestStore, *, budget: int = 15_000, today: date | None = None,
                 on_step: Callable[[StepResult], None] | None = None):
        self.src, self.store = source, store
        self.budget = Budget(budget, self._calls)
        self.today = today or date.today()
        self.on_step = on_step or (lambda r: None)
        self._units = 0

    # ---- 공통 ----------------------------------------------------------------------------
    def _calls(self) -> int:
        return int(getattr(self.src, "calls", 0) or 0)

    def _guard(self) -> None:
        """단위 작업마다 부른다. 예산과 (50번마다) Kill Switch를 본다."""
        self.budget.check()
        self._units += 1
        if self._units % 50 == 0:
            active, reason = self.store.kill_switch()
            if active:
                raise KillSwitchOn(reason or "Kill Switch")

    def run(self, mode: str = "daily", steps: tuple[str, ...] = STEPS, years: int = 3,
            documents: bool = True) -> RunReport:
        report = RunReport(run_uid=f"ing-{uuid.uuid4().hex[:12]}", mode=mode)
        active, reason = self.store.kill_switch()
        if active:
            rid = self.store.start_run(report.run_uid, mode, "all", self.src.name)
            self.store.finish_run(rid, status="SKIPPED", calls=0, rows=0, error=f"Kill Switch: {reason}")
            report.steps.append(StepResult("all", "SKIPPED", error=f"Kill Switch: {reason}"))
            return report
        for step in STEPS:
            if step not in steps or (step == "documents" and not documents):
                continue
            res = StepResult(step)
            rid = self.store.start_run(report.run_uid, mode, step, self.src.name)
            before = self._calls()
            try:
                if self.budget.left <= 0:
                    raise BudgetExhausted()
                fn = getattr(self, f"_step_{step}")
                res.rows, res.remaining = fn(mode=mode, years=years)
                if res.remaining:
                    res.status = "PARTIAL"
            except BudgetExhausted:
                res.status = "PARTIAL"
                res.remaining = res.remaining or -1          # -1 = 시작도 못 함(대상 수를 세지 못함)
            except KillSwitchOn as e:
                res.status, res.error = "SKIPPED", f"Kill Switch: {e}"
            except Exception as e:                            # 한 단계 실패가 다른 단계를 막지 않는다
                logger.exception("수집 단계 실패: %s", step)
                res.status, res.error = "FAILED", f"{type(e).__name__}: {e}"
            res.calls = self._calls() - before
            self.store.finish_run(rid, status=res.status, calls=res.calls, rows=res.rows,
                                  remaining=max(res.remaining, 0), error=res.error)
            report.steps.append(res)
            self.on_step(res)
            if res.status == "SKIPPED":
                break
        return report

    # ---- 단계 -----------------------------------------------------------------------------
    def _step_companies(self, **_) -> tuple[int, int]:
        rows = [c for c in self.src.companies() if c.get("stock_code")]
        n = self.store.upsert_companies(rows, self.today)
        # 목록 전체를 받았을 때만 상장폐지를 표시한다(빈 응답·부분 응답으로 전부 지워지는 사고를 막는다)
        if len(rows) >= 0.8 * max(1, self.store.count(T.company)):
            self.store.mark_delisted({c["corp_code"] for c in rows}, self.today)
        return n, 0

    def _filing_payload(self, r: dict) -> dict | None:
        code, year = report_kind(r.get("report_nm", ""))
        if not code:
            return None
        return {"rcept_no": r["rcept_no"], "corp_code": r["corp_code"], "corp_name": r.get("corp_name"),
                "stock_code": r.get("stock_code") or None, "report_nm": r["report_nm"], "reprt_code": code,
                "bsns_year": year, "rcept_dt": r["rcept_dt"], "rm": r.get("rm") or None,
                "is_correction": "정정" in r["report_nm"] or "정" in (r.get("rm") or ""),
                "has_document": bool(r.get("hasDocument")), "financial_done": False}

    def _step_filings(self, mode: str, years: int, **_) -> tuple[int, int]:
        rows: list[dict] = []
        remaining = 0
        if mode == "backfill":
            # 회사별 지난 정기공시. 공시가 하나도 적재되지 않은 회사부터(이어 하기)
            with self.store.engine.connect() as conn:
                done = {r.corp_code for r in conn.execute(sa.select(T.filing.c.corp_code).distinct())}
                corps = [r.corp_code for r in conn.execute(
                    sa.select(T.company.c.corp_code).where(T.company.c.listed))]
            todo = [c for c in corps if c not in done]
            for k, corp in enumerate(todo):
                try:
                    self._guard()
                except BudgetExhausted:
                    remaining = len(todo) - k
                    break
                try:
                    lst = self.src.filings(corp)
                except SourceError:
                    continue
                cutoff = f"{self.today.year - years}0101"
                corp_name = None
                rows += [{**f, "corp_code": corp, "corp_name": corp_name} for f in lst if f["rcept_dt"] >= cutoff]
        else:
            self._guard()
            rows = self.src.recent_filings()
        payload = [p for r in rows if (p := self._filing_payload(r))]
        # has_document·financial_done은 이미 true인 값을 덮어쓰지 않는다(update 목록에서 뺀다)
        n = self.store.upsert(T.filing, payload, ["rcept_no"], ["report_nm", "rm", "is_correction"])
        return n, remaining

    def _step_market(self, **_) -> tuple[int, int]:
        self._guard()
        history = self.src.market_history()
        last = self.store.latest_market_dates()
        payload, market_of = [], {}
        for code, rows in history.items():
            since = last.get(code, "")
            for r in rows:
                if not r.get("basDt") or r["basDt"] <= since:
                    continue
                payload.append({"stock_code": code, "bas_dt": r["basDt"], "itms_nm": r.get("itmsNm"),
                                "mrkt_ctg": (r.get("mrktCtg") or "").upper() or None, "clpr": _int(r.get("clpr")),
                                "lstg_st_cnt": _int(r.get("lstgStCnt")), "mrkt_tot_amt": _int(r.get("mrktTotAmt"))})
            if rows:
                market_of[code] = (max(rows, key=lambda x: x.get("basDt", "")).get("mrktCtg") or "").upper() or None
        n = self.store.upsert(T.market_daily, payload, ["stock_code", "bas_dt"],
                              ["itms_nm", "mrkt_ctg", "clpr", "lstg_st_cnt", "mrkt_tot_amt"])
        # 회사의 시장 구분은 시세가 정본이다(상장 시장 이전이 있으면 따라간다)
        with self.store.engine.begin() as conn:
            for code, m in market_of.items():
                if m in ("KOSPI", "KOSDAQ", "KONEX"):
                    conn.execute(T.company.update().where(T.company.c.stock_code == code).values(market=m))
        return n, 0

    def _step_index(self, **_) -> tuple[int, int]:
        payload = []
        for name in INDEX_NAMES:
            self._guard()
            for r in self.src.index_series(name):
                if r.get("basDt") and r.get("clpr") not in (None, ""):
                    payload.append({"idx_nm": name, "bas_dt": r["basDt"], "clpr": float(str(r["clpr"]).replace(",", ""))})
        return self.store.upsert(T.index_daily, payload, ["idx_nm", "bas_dt"], ["clpr"]), 0

    def _step_financials(self, **_) -> tuple[int, int]:
        """재무를 아직 안 받은 정기공시. 같은 회사·연도·보고서의 최신 접수(정정 포함)만 한 번 받는다."""
        with self.store.engine.connect() as conn:
            todo = conn.execute(sa.select(T.filing).where(~T.filing.c.financial_done)
                                .order_by(T.filing.c.rcept_dt.desc())).mappings().all()
        seen, rows, remaining = set(), 0, 0
        for k, f in enumerate(todo):
            key = (f["corp_code"], f["bsns_year"], f["reprt_code"])
            if key in seen:
                self._mark(f["rcept_no"], financial_done=True)    # 같은 기간의 이전 접수는 최신 것으로 대신한다
                continue
            seen.add(key)
            try:
                self._guard()
            except BudgetExhausted:
                remaining = len(todo) - k
                break
            try:
                lines, fs = self.src.financials(*key)
            except SourceError:
                old = (self.today - _d(f["rcept_dt"])).days > FINANCIAL_GIVE_UP_DAYS
                if old:
                    self._mark(f["rcept_no"], financial_done=True)
                continue
            payload = [{"corp_code": key[0], "bsns_year": key[1], "reprt_code": key[2], "fs_div": fs,
                        "rcept_no": ln.get("rcept_no") or f["rcept_no"], "sj_div": ln.get("sj_div") or "",
                        "account_id": ln.get("account_id"), "account_nm": ln.get("account_nm") or "",
                        "ord": _int(ln.get("ord")) or 0, **{c: ln.get(c) for c in T.FIN_FIELDS}} for ln in lines]
            rows += self.store.upsert(T.financial_line, payload,
                                      ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "account_nm", "ord"],
                                      ["rcept_no", "account_id", *T.FIN_FIELDS])
            self._mark(f["rcept_no"], financial_done=True)
        return rows, remaining

    def _step_induty(self, **_) -> tuple[int, int]:
        stale = self.today - timedelta(days=INDUTY_RECHECK_DAYS)
        last = self.store.latest_market_dates()
        with self.store.engine.connect() as conn:
            caps = {r.stock_code: r.mrkt_tot_amt or 0 for r in conn.execute(
                sa.select(T.market_daily.c.stock_code, T.market_daily.c.bas_dt, T.market_daily.c.mrkt_tot_amt))
                if last.get(r.stock_code) == r.bas_dt}
            todo = conn.execute(sa.select(T.company.c.corp_code, T.company.c.stock_code).where(
                T.company.c.listed & (T.company.c.induty_checked.is_(None) | (T.company.c.induty_checked < stale)))).all()
        todo = sorted(todo, key=lambda r: -caps.get(r.stock_code, 0))       # 업종 지도에 크게 보이는 회사부터
        n, remaining = 0, 0
        for k, r in enumerate(todo):
            try:
                self._guard()
            except BudgetExhausted:
                remaining = len(todo) - k
                break
            code = self.src.induty_code(r.corp_code)
            with self.store.engine.begin() as conn:
                conn.execute(T.company.update().where(T.company.c.corp_code == r.corp_code)
                             .values(induty_code=code, induty_checked=self.today))
            n += 1
        return n, remaining

    def _step_documents(self, **_) -> tuple[int, int]:
        """최근 90일 정기공시 원문. 원문은 소스의 디스크 캐시에 남고 여기서는 보유 여부만 표시한다."""
        cutoff = (self.today - timedelta(days=90)).strftime("%Y%m%d")
        with self.store.engine.connect() as conn:
            todo = conn.execute(sa.select(T.filing.c.rcept_no).where(
                ~T.filing.c.has_document & (T.filing.c.rcept_dt >= cutoff)).order_by(T.filing.c.rcept_dt.desc())).all()
        n, remaining = 0, 0
        for k, r in enumerate(todo):
            try:
                self._guard()
            except BudgetExhausted:
                remaining = len(todo) - k
                break
            try:
                self.src.document(r.rcept_no)
            except SourceError:
                continue
            self._mark(r.rcept_no, has_document=True)
            n += 1
        return n, remaining

    def _mark(self, rcept_no: str, **vals) -> None:
        with self.store.engine.begin() as conn:
            conn.execute(T.filing.update().where(T.filing.c.rcept_no == rcept_no).values(**vals))


def _int(v) -> int | None:
    if v in (None, "", "-"):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except ValueError:
        return None


def _d(yyyymmdd: str) -> date:
    return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
