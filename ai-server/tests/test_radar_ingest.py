"""#3 일일 수집 파이프라인 테스트. 샘플 원천 + 인메모리 SQLite — 키·MariaDB 없이 돈다. 실행: python -m unittest -v"""
import unittest
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from radar.company import search_companies
from radar.config import Settings
from radar.ingest import IngestedSource, Ingestor, IngestStore
from radar.ingest import tables as T
from radar.market import market_overview
from radar.sources import SampleSource

TODAY = date(2026, 10, 15)


def engine():
    e = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    T.metadata.create_all(e)
    return e


def sample():
    return SampleSource(Settings().sample_dir)


def counts(store: IngestStore) -> dict:
    return {t.name: store.count(t) for t in (T.company, T.filing, T.financial_line, T.market_daily)}


class DailyIngestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = engine()
        cls.store = IngestStore(cls.engine)
        cls.first = Ingestor(sample(), cls.store, today=TODAY).run("daily")
        cls.after_first = counts(cls.store)
        cls.second = Ingestor(sample(), cls.store, today=TODAY).run("daily")

    def test_all_steps_done_and_loaded(self):
        self.assertTrue(all(s.status == "DONE" for s in self.first.steps), self.first.summary())
        c = self.after_first
        self.assertEqual(c["ingest_company"], 46)
        self.assertEqual(c["ingest_filing"], 23)
        self.assertEqual(c["ingest_market_daily"], 46 * 262)
        self.assertGreater(c["ingest_financial_line"], 0)

    def test_second_run_is_idempotent(self):
        self.assertEqual(counts(self.store), self.after_first)
        market = next(s for s in self.second.steps if s.step == "market")
        self.assertEqual(market.rows, 0)                         # 저장된 마지막 날짜 이후만 쓴다

    def test_run_log(self):
        runs = self.store.recent_runs(100)
        self.assertEqual({r["step"] for r in runs if r["run_uid"] == self.first.run_uid},
                         {"companies", "filings", "market", "index", "financials", "induty", "documents"})
        self.assertTrue(all(r["finished_at"] for r in runs))

    def test_company_market_and_induty_loaded(self):
        with self.engine.connect() as conn:
            r = conn.execute(sa.select(T.company).where(T.company.c.corp_code == "00999001")).mappings().first()
        self.assertEqual((r["market"], r["induty_code"], r["first_seen"]), ("KOSDAQ", "20129", TODAY))


class ReadSideTest(unittest.TestCase):
    """적재 DB를 읽어도 원천을 직접 읽은 것과 같은 결과가 나와야 한다(화면이 수집 전후로 달라지지 않는다)."""

    @classmethod
    def setUpClass(cls):
        cls.engine = engine()
        Ingestor(sample(), IngestStore(cls.engine), today=TODAY).run("daily")
        cls.db = IngestedSource(sample(), cls.engine)

    def test_market_overview_equivalent(self):
        a, b = market_overview(sample(), "ALL"), market_overview(self.db, "ALL")
        self.assertEqual(a["capitalization"]["total"], b["capitalization"]["total"])
        self.assertEqual(a["capitalization"]["series"], b["capitalization"]["series"])
        self.assertEqual(a["sectors"], b["sectors"])
        self.assertEqual(a["markets"], b["markets"])
        self.assertEqual([r["rceptNo"] for r in a["recentFilings"]], [r["rceptNo"] for r in b["recentFilings"]])

    def test_company_search_equivalent(self):
        self.assertEqual(search_companies(sample(), ""), search_companies(self.db, ""))

    def test_financials_from_db_without_source_calls(self):
        src = sample()
        db = IngestedSource(src, self.engine)
        rows, fs = db.financials("00999001", 2025, "11011")
        self.assertEqual(fs, "CFS")
        self.assertEqual(src.calls, 0)                           # 원천을 부르지 않았다
        want, _ = sample().financials("00999001", 2025, "11011")
        self.assertEqual({r["account_nm"]: r["thstrm_amount"] for r in rows},
                         {r["account_nm"]: r["thstrm_amount"] for r in want})

    def test_empty_db_falls_back_to_source(self):
        empty = IngestedSource(sample(), engine())
        self.assertEqual(len(empty.companies()), 46)
        self.assertEqual(len(empty.market_history()), 46)


class BudgetKillSwitchTest(unittest.TestCase):
    def test_budget_exhaustion_resumes_next_run(self):
        store = IngestStore(engine())
        first = Ingestor(sample(), store, budget=60, today=TODAY).run("daily")
        status = {s.step: s.status for s in first.steps}
        self.assertEqual(status["financials"], "PARTIAL")        # 시세가 예산을 다 썼다
        with store.engine.connect() as conn:
            left = conn.execute(sa.select(sa.func.count()).select_from(T.filing).where(~T.filing.c.financial_done)).scalar()
        self.assertGreater(left, 0)
        second = Ingestor(sample(), store, budget=10_000, today=TODAY).run("daily")
        self.assertEqual({s.step: s.status for s in second.steps}["financials"], "DONE")
        self.assertGreater(store.count(T.financial_line), 0)

    def test_kill_switch_skips_everything(self):
        e = engine()
        with e.begin() as conn:
            conn.execute(T.kill_switch_status.insert().values(active=True, reason="훈련", toggled_by="pytest"))
        store = IngestStore(e)
        rep = Ingestor(sample(), store, today=TODAY).run("daily")
        self.assertEqual([s.status for s in rep.steps], ["SKIPPED"])
        self.assertEqual(store.count(T.company), 0)
        self.assertEqual(store.recent_runs()[0]["status"], "SKIPPED")


class NewListingTest(unittest.TestCase):
    def test_company_first_seen_after_initial_load_is_new(self):
        e = engine()
        store = IngestStore(e)
        Ingestor(sample(), store, today=TODAY - timedelta(days=10), budget=10_000).run("daily", steps=("companies",))
        self.assertEqual(IngestedSource(sample(), e).new_listings(), [])        # 첫 적재분은 신규가 아니다
        store.upsert_companies([{"corp_code": "00555001", "corp_name": "새상장(가상)", "stock_code": "555001",
                                 "market": "KOSDAQ"}], date.today())
        names = [r["corp_name"] for r in IngestedSource(sample(), e).new_listings()]
        self.assertEqual(names, ["새상장(가상)"])


if __name__ == "__main__":
    unittest.main()
