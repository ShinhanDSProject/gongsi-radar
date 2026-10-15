"""시장 지표(TTM·PER·PBR) 계산식. 실행: python -m unittest -v"""
import unittest

from radar.config import Settings
from radar.schemas import Valuation
from radar.sources import SampleSource, SourceError
from radar.valuation import compute_valuation, metric

AS_OF = "2026-10-15"
CO = {"corp_code": "X1", "corp_name": "가상테스트", "stock_code": "000001"}


def row(sj, aid, nm, **amts):
    r = {"rcept_no": amts.pop("rcept_no", "20260301000001"), "bsns_year": "2025", "sj_div": sj, "account_id": aid,
         "account_nm": nm}
    r.update({k: str(v) for k, v in amts.items()})
    return r


def annual(owner=True, ni_owner=120, ni=130, eq_owner=1000, eq=1100, rcept_no="20260301000001"):
    rows = [row("IS", "ifrs-full_Revenue", "매출액", thstrm_amount=1000, rcept_no=rcept_no),
            row("IS", "dart_OperatingIncomeLoss", "영업이익", thstrm_amount=100, rcept_no=rcept_no),
            row("IS", "ifrs-full_ProfitLoss", "당기순이익", thstrm_amount=ni, rcept_no=rcept_no),
            row("BS", "ifrs-full_Equity", "자본총계", thstrm_amount=eq, rcept_no=rcept_no)]
    if owner:
        rows += [row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익",
                     thstrm_amount=ni_owner, rcept_no=rcept_no),
                 row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 자본",
                     thstrm_amount=eq_owner, rcept_no=rcept_no)]
    return rows


def half(owner=True, rcept_no="20260814000001"):
    rows = [row("IS", "ifrs-full_Revenue", "매출액", thstrm_add_amount=600, frmtrm_add_amount=500, rcept_no=rcept_no),
            row("IS", "dart_OperatingIncomeLoss", "영업이익", thstrm_add_amount=70, frmtrm_add_amount=40, rcept_no=rcept_no),
            row("IS", "ifrs-full_ProfitLoss", "당기순이익", thstrm_add_amount=60, frmtrm_add_amount=50, rcept_no=rcept_no),
            row("BS", "ifrs-full_Equity", "자본총계", thstrm_amount=1150, rcept_no=rcept_no)]
    if owner:
        rows += [row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익",
                     thstrm_add_amount=55, frmtrm_add_amount=45, rcept_no=rcept_no),
                 row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 자본",
                     thstrm_amount=1040, rcept_no=rcept_no)]
    for r in rows:
        r["bsns_year"] = "2026"
    return rows


class FakeSource:
    name = "fake"

    def __init__(self, data: dict, prices=None):
        self.data, self.prices = data, prices

    def financials(self, corp, year, code):
        if (year, code) in self.data:
            return self.data[(year, code)]
        raise SourceError("013")

    def market(self, stock_code):
        return self.prices if self.prices is not None else [
            {"basDt": "20261014", "itmsNm": "가상테스트", "clpr": "30", "lstgStCnt": "100"},
            {"basDt": "20261013", "itmsNm": "가상테스트", "clpr": "29", "lstgStCnt": "100"},
            {"basDt": "20261016", "itmsNm": "가상테스트", "clpr": "99", "lstgStCnt": "100"}]  # 기준일 뒤: 쓰면 안 됨


def m(val, fid):
    return next(x for x in val["metrics"] if x["id"] == fid)


class ValuationTest(unittest.TestCase):
    def test_ttm_per_pbr_with_owner_accounts(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(), "CFS"), (2026, "11012"): (half(), "CFS")}), CO, AS_OF)
        Valuation.model_validate(v)
        self.assertEqual(v["interim"], {"year": 2026, "reprtCode": "11012", "rceptNo": "20260814000001"})
        self.assertEqual(v["price"]["basDt"], "20261014")          # 기준일 이후 시세는 쓰지 않음
        self.assertEqual(metric(v, "market_cap"), 3000)
        self.assertEqual(metric(v, "ttm_revenue"), 1000 + 600 - 500)
        self.assertEqual(metric(v, "ttm_op"), 100 + 70 - 40)
        self.assertEqual(metric(v, "ttm_ni_owner"), 120 + 55 - 45)  # 지배주주 계정 사용(전체 130이 아님)
        self.assertEqual(metric(v, "per_ttm"), round(3000 / 130, 2))
        self.assertEqual(metric(v, "per_annual"), 25.0)
        self.assertEqual(metric(v, "pbr"), round(3000 / 1040, 2))  # 최근 기말 = 반기말 지배주주 자본
        ttm = m(v, "ttm_ni_owner")
        self.assertEqual([i["value"] for i in ttm["inputs"]], [120, 55, 45])
        self.assertEqual(ttm["inputs"][1]["source"]["field"], "thstrm_add_amount")
        self.assertEqual(ttm["inputs"][2]["source"]["field"], "frmtrm_add_amount")
        self.assertFalse(any("대체 계정" in n for n in ttm["notes"]))

    def test_fallback_to_total_accounts_noted(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(owner=False), "OFS"),
                                          (2026, "11012"): (half(owner=False), "OFS")}), CO, AS_OF)
        self.assertEqual(metric(v, "ttm_ni_owner"), 130 + 60 - 50)
        ttm = m(v, "ttm_ni_owner")
        self.assertTrue(all("대체 계정" in i["note"] for i in ttm["inputs"]))
        self.assertTrue(any("대체 계정" in n for n in ttm["notes"]))
        self.assertIn("대체 계정", m(v, "per_annual")["inputs"][1]["note"])
        self.assertIn("대체 계정", m(v, "pbr")["inputs"][1]["note"])
        self.assertEqual(metric(v, "pbr"), round(3000 / 1150, 2))

    def test_owner_account_only_in_annual_uses_total_for_both(self):
        # 연간에만 지배주주 계정이 있으면 TTM은 연간·중간 모두 전체 계정으로 맞춘다(섞지 않음)
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(), "CFS"),
                                          (2026, "11012"): (half(owner=False), "CFS")}), CO, AS_OF)
        self.assertEqual(metric(v, "ttm_ni_owner"), 130 + 60 - 50)

    def test_earnings_not_positive_not_computed(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(ni_owner=-20), "CFS"),
                                          (2026, "11012"): (half(), "CFS")}), CO, AS_OF)
        pa = m(v, "per_annual")
        self.assertEqual((pa["status"], pa["result"]), ("계산 안 함", None))
        self.assertIn("0 이하", pa["reason"])
        self.assertEqual(metric(v, "ttm_ni_owner"), -20 + 55 - 45)
        self.assertEqual(m(v, "per_ttm")["status"], "계산 안 함")

    def test_missing_price_is_not_zero(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(), "CFS")}, prices=[]), CO, AS_OF)
        for fid in ("market_cap", "per_ttm", "per_annual", "pbr"):
            f = m(v, fid)
            self.assertIsNone(f["result"])
            self.assertEqual(f["status"], "계산 안 함")
            self.assertTrue(f["reason"])
        self.assertIsNone(v["price"])
        self.assertIsNone(v["interim"])
        self.assertEqual(metric(v, "ttm_revenue"), 1000)  # 중간보고서가 없으면 최근 연간 그대로(사유를 notes에)
        self.assertTrue(any("중간보고서" in n for n in m(v, "ttm_revenue")["notes"]))

    def test_interim_scope_mismatch_skipped(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(), "OFS"), (2026, "11014"): (half(), "CFS"),
                                          (2026, "11012"): (half(), "OFS")}), CO, AS_OF)
        self.assertEqual(v["interim"]["reprtCode"], "11012")       # 3분기(CFS)는 범위가 달라 건너뜀
        self.assertTrue(any("범위가 달라" in n for n in v["notes"]))

    def test_filings_after_as_of_ignored(self):
        v = compute_valuation(FakeSource({(2025, "11011"): (annual(), "CFS"), (2026, "11012"): (half(), "CFS")}),
                              CO, "2026-08-01")
        self.assertIsNone(v["interim"])                            # 반기보고서 접수(8/14) 전 기준일

    def test_no_annual_returns_none(self):
        self.assertIsNone(compute_valuation(FakeSource({}), CO, AS_OF))

    def test_sample_company(self):
        s = SampleSource(Settings().sample_dir)
        v = compute_valuation(s, s.resolve("999001"), AS_OF)
        self.assertEqual(v["marketSource"], "sample")
        self.assertEqual(metric(v, "ttm_revenue"), 1_074_000 * 10**6)
        self.assertEqual(metric(v, "ttm_ni_owner"), 17_500 * 10**6)
        cap = v["price"]["close"] * 20_000_000
        self.assertEqual(metric(v, "market_cap"), cap)
        self.assertEqual(metric(v, "pbr"), round(cap / (1_415_000 * 10**6), 2))
        self.assertEqual(m(v, "per_annual")["inputs"][1]["value"], 12_100 * 10**6)


if __name__ == "__main__":
    unittest.main()
