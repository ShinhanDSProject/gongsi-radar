"""시장 화면(radar/market.py) 테스트. 실행: python -m unittest -v"""
import json
import unittest

from radar.config import Settings
from radar.market import (cap_series, ksic_division, ksic_section, market_overview, period_changes, proxy_index,
                          sector_tree)
from radar.sources import SampleSource
from radar.verify import banned_hits


def sample() -> SampleSource:
    return SampleSource(Settings().sample_dir)


class RulesTest(unittest.TestCase):
    def test_ksic_mapping(self):
        self.assertEqual(ksic_section("20129"), ("C", "제조업"))
        self.assertEqual(ksic_section("64191")[0], "K")
        self.assertEqual(ksic_section("35200")[0], "D")
        self.assertEqual(ksic_section(None), ("?", "업종 미확인"))
        self.assertEqual(ksic_division("26110")[0], "26")

    def test_period_changes_need_enough_history(self):
        s = [{"d": "2026-10-01", "v": 100.0}, {"d": "2026-10-02", "v": 110.0}]
        ch = {c["period"]: c for c in period_changes(s)}
        self.assertEqual((ch["1D"]["pct"], ch["1D"]["delta"]), (10.0, 10.0))
        # 1년 전 데이터가 없으면 0이 아니라 계산하지 않음 + 사유
        self.assertIsNone(ch["1Y"]["pct"])
        self.assertEqual(ch["1Y"]["reason"], "기간 데이터 부족")

    def test_cap_series_carries_forward_missing_day(self):
        hist = {"A": [{"basDt": "20261001", "mrktTotAmt": "100"}, {"basDt": "20261002", "mrktTotAmt": "110"}],
                "B": [{"basDt": "20261001", "mrktTotAmt": "50"}]}           # B는 10월 2일 시세가 빠졌다
        self.assertEqual([p["v"] for p in cap_series(hist, ["A", "B"])], [150, 160])
        self.assertEqual(proxy_index([{"d": "a", "v": 200}, {"d": "b", "v": 250}])[-1]["v"], 1250.0)

    def test_sector_tree_sums_and_shares(self):
        t = sector_tree([{"corp_code": "1", "corp_name": "a", "stock_code": "1", "induty_code": "20129", "cap": 300},
                         {"corp_code": "2", "corp_name": "b", "stock_code": "2", "induty_code": "26110", "cap": 100},
                         {"corp_code": "3", "corp_name": "c", "stock_code": "3", "induty_code": "64191", "cap": 100}])
        self.assertEqual((t["value"], t["count"]), (500, 3))
        c = t["children"][0]
        self.assertEqual((c["code"], c["value"], c["share"]), ("C", 400, 80.0))
        self.assertEqual([d["code"] for d in c["children"]], ["20", "26"])
        self.assertEqual(c["children"][0]["children"][0]["corpCode"], "1")


class OverviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all = market_overview(sample(), "ALL")

    def test_shape_and_counts(self):
        o = self.all
        self.assertEqual(o["asOf"], "2026-10-14")
        self.assertEqual({m["code"]: m["count"] for m in o["markets"]}["ALL"], 46)
        self.assertEqual(sum(m["count"] for m in o["markets"] if m["code"] != "ALL"), 46)
        cap = o["capitalization"]
        self.assertEqual(cap["total"], sum(n["value"] for n in o["sectors"]["children"]))
        self.assertEqual(cap["availableRanges"], ["1Y"])
        self.assertIn("1년치", cap["rangeNote"])
        self.assertTrue(all(c["pct"] is not None for c in cap["changes"]))

    def test_proxy_index_is_labelled(self):
        for idx in self.all["indices"]:
            self.assertEqual(idx["kind"], "proxy")
            self.assertIn("(대체)", idx["name"])
            self.assertIn("공식", idx["note"])
            self.assertEqual(idx["series"][0]["v"], 1000.0)

    def test_market_filter_applies_to_cap_sectors_filings(self):
        kq = market_overview(sample(), "KOSDAQ")
        self.assertLess(kq["capitalization"]["total"], self.all["capitalization"]["total"])
        self.assertEqual(kq["indices"], self.all["indices"])          # 지수는 필터와 무관
        names = {r["corpName"] for r in kq["recentFilings"]}
        self.assertNotIn("가상은행㈜", names)                          # 유가증권시장 종목
        with self.assertRaises(ValueError):
            market_overview(sample(), "NYSE")

    def test_recent_filings(self):
        rows = self.all["recentFilings"]
        self.assertEqual(rows, sorted(rows, key=lambda r: (r["rceptDt"], r["rceptNo"]), reverse=True))
        self.assertTrue(any(r["isCorrection"] for r in rows))
        main = next(r for r in rows if r["corpCode"] == "00999001" and r["reprtCode"] == "11011")
        self.assertTrue(main["hasDocument"])
        self.assertEqual(main["bsnsYear"], 2025)

    def test_no_judgement_words(self):
        self.assertEqual(banned_hits(json.dumps(self.all, ensure_ascii=False)), [])


if __name__ == "__main__":
    unittest.main()
