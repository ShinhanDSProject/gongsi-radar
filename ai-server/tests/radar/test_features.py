"""확장 기능: 계정 계산식, 사업 지표 검산, 지배구조 변동, 기업 목록·상세, 단계별 호출. 실행: python -m unittest -v"""
import copy
import os
import tempfile
import unittest
from pathlib import Path

from radar.pipeline import graph as g
from radar.insights.business import extract_business
from radar.insights.document import document_insights
from radar.config import ROOT, Settings
from radar.numbers.formula import texts
from radar.insights.governance import build_governance, known_names
from radar.parsing.parser import parse_filing_zip
from radar.pipeline.schemas import Report
from radar.pipeline.run import run_analysis
from radar.sources.sample import SampleSource
from radar.evidence.verify import banned_hits

DATA = ROOT.parent / "samples" / "data" / "filings"
OLD, NEW = "20250318000412", "20260317000388"
REQ = {"company": "999001", "bsns_year": 2025, "reprt_code": "11011"}


def load(rno):
    return parse_filing_zip((DATA / f"{rno}.zip").read_bytes(), rno)


def settings(tmp: str) -> Settings:
    s = Settings()
    s.source, s.out_dir, s.llm_api_key = "sample", Path(tmp), None
    return s


def sample() -> SampleSource:
    return SampleSource(Settings().sample_dir)


class ReportExtensionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = run_analysis(dict(REQ), settings(tempfile.mkdtemp()))

    def acct(self, nm):
        return next(a for a in self.rep["accounts"] if a["account_nm"] == nm)

    def f(self, a, fid):
        return next(x for x in a["formulas"] if x["id"] == fid)

    def test_yoy_formula_equals_account_value(self):
        for a in self.rep["accounts"]:
            self.assertEqual(self.f(a, "yoy")["result"], a["yoy_pct"], a["account_nm"])
            self.assertEqual(self.f(a, "delta")["result"], a["delta"])
            self.assertNotIn("_src", a)
        d = self.f(self.acct("영업이익"), "delta")
        self.assertEqual([i["value"] for i in d["inputs"]], [40_500 * 10**6, 121_000 * 10**6])
        self.assertEqual(d["inputs"][0]["source"]["rceptNo"], NEW)
        self.assertEqual(d["inputs"][0]["source"]["field"], "thstrm_amount")

    def test_robust_z_formula_inputs(self):
        a = self.acct("영업이익")
        z = self.f(a, "robust_z")
        ins = {i["name"]: i["value"] for i in z["inputs"]}
        self.assertEqual(ins["n"], 29)
        self.assertEqual(z["result"], a["robust_z"])
        recomputed = 0.6745 * (ins["x(이 회사 YoY 변화율)"] - ins["피어 중앙값"]) / ins["MAD"]
        self.assertAlmostEqual(recomputed, a["robust_z"], places=1)
        self.assertEqual(z["inputs"][1]["source"]["kind"], "업종 피어")
        self.assertFalse(any(x["id"] == "robust_z" for x in self.acct("재고자산")["formulas"]))  # 피어 없는 계정

    def test_materiality_formula(self):
        mf = self.f(self.acct("재고자산"), "materiality")
        self.assertEqual(mf["result"], round(119_000 / 1_012_000 * 100, 2))
        self.assertIn("기준 충족", mf["notes"])
        self.assertFalse(any(x["id"] == "materiality" for x in self.acct("영업이익")["formulas"]))  # 핵심 계정
        owner = self.acct("지배기업의 소유주에게 귀속되는 당기순이익")
        self.assertEqual(owner["flags"], [])                       # 플래그 대상 아님(FLAG_EXCLUDE)
        self.assertNotIn(owner["key"], {r["account_key"] for r in self.rep["relations"]})

    def test_report_has_extensions(self):
        r = self.rep
        self.assertEqual(r["business"]["summary"], {"passed": 7, "failed": 1, "unchecked": 0})
        self.assertEqual(len(r["governance"]["changes"]), 5)
        self.assertEqual(r["valuation"]["annual"]["year"], 2025)
        self.assertTrue(r["title"].startswith("샘플소재㈜"))
        self.assertTrue(r["summary"].startswith("변경 문단"))
        self.assertIn(f"dart:{NEW}", r["citations"])
        self.assertIn("market-data:999001", r["citations"])
        self.assertTrue(r["reviewPassed"])
        self.assertTrue(any("고순도 황산니켈" in i for i in r["reviewIssues"]))
        self.assertTrue(any(i.startswith("C01 검토 필요") for i in r["reviewIssues"]))
        self.assertTrue(r["generatedAt"])

    def test_no_banned_words_in_generated_text(self):
        gen = texts([self.rep["business"], self.rep["governance"], self.rep["valuation"],
                     [a["formulas"] for a in self.rep["accounts"]], self.rep["summary"], self.rep["title"],
                     self.rep["reviewIssues"]])
        self.assertGreater(len(gen), 100)
        self.assertEqual([h for t in gen for h in banned_hits(t)], [])
        ins = document_insights(sample(), "00999001")         # 기업 상세에 붙는 문서 파생 정보
        self.assertEqual([h for t in texts(ins) for h in banned_hits(t)], [])

    def test_old_report_without_new_keys_still_validates(self):
        old = copy.deepcopy(self.rep)
        for k in ("business", "governance", "valuation", "title", "summary", "citations", "toolCalls",
                  "reviewPassed", "reviewIssues", "generatedAt", "agents"):
            old.pop(k)
        for a in old["accounts"]:
            a.pop("formulas")
        Report.model_validate(old)


class BusinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = extract_business(load(OLD), load(NEW), {2024: 1_284_000 * 10**6, 2025: 1_012_000 * 10**6}, (2024, 2025))

    def group(self, kind):
        return next(x for x in self.b["groups"] if x["kind"] == kind)

    def test_order_row_fails_arithmetic(self):
        grp = self.group("수주")
        rows = {r["label"]: r for r in grp["rows"]}
        self.assertEqual(rows["고순도 황산니켈"]["status"], "검산 불일치")
        bad = [c for c in rows["고순도 황산니켈"]["checks"] if c["status"] == "fail"]
        self.assertEqual(len(bad), 1)
        self.assertIn("2025", bad[0]["name"])
        self.assertEqual(rows["NCM 전구체"]["status"], "검산 통과")
        self.assertEqual(rows["LFP 전구체"]["status"], "검산 통과")
        self.assertTrue(grp["currentPid"].startswith(f"{NEW}:II-4:T"))

    def test_backlog_matches_text(self):
        grp = self.group("수주")
        checks = {c["name"]: c["status"] for c in grp["checks"]}
        self.assertEqual(checks["수주잔고 합계↔본문(2024)"], "pass")
        self.assertEqual(checks["수주잔고 합계↔본문(2025)"], "pass")  # 불일치 행도 표 값 그대로 합산(631,000)
        tot = next(f for f in grp["formulas"] if f["id"] == "backlog_total_2025")
        self.assertEqual(tot["result"], 631_000)
        self.assertEqual(tot["inputs"][0]["source"]["kind"], "원문 표")

    def test_segment_checks(self):
        grp = self.group("부문 매출")
        self.assertTrue(all(c["status"] == "pass" for c in grp["checks"]), grp["checks"])
        self.assertTrue(all(r["status"] == "검산 통과" for r in grp["rows"]))
        ncm = next(r for r in grp["rows"] if r["label"] == "NCM 전구체")
        self.assertEqual(ncm["values"][0]["yoyPct"], round((812_000 - 1_050_000) / 1_050_000 * 100, 2))
        lfp = next(r for r in grp["rows"] if r["label"] == "LFP 전구체")
        self.assertIsNone(lfp["values"][0]["prior"])                  # 전기에 없던 항목: 0이 아니라 None
        self.assertIsNone(lfp["values"][0]["yoyPct"])

    def test_capacity_checks_and_weighted_utilization(self):
        grp = self.group("생산능력·가동률")
        self.assertEqual(grp["unit"], "톤")
        self.assertTrue(all(c["status"] == "pass" for c in grp["checks"]), grp["checks"])
        w = next(f for f in grp["formulas"] if f["id"] == "utilization_wavg_2025")
        self.assertEqual(w["result"], round((30_000 * 64.0 + 40_000 * 59.1) / 70_000, 2))

    def test_unstructured_tables_ignored(self):
        kinds = [x["kind"] for x in self.b["groups"]]
        self.assertEqual(kinds, ["부문 매출", "수주", "생산능력·가동률"])  # 요약재무·거래 표는 읽지 않음


class GovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = sample()
        cls.known = known_names([c for c in s.companies() if c["corp_code"] != "00999001"])
        cls.gv = build_governance(s.governance("00999001", 2025, "11011"), s.governance("00999001", 2024, "11011"),
                                  cls.known, s.resolve("999001"))

    def test_shareholder_changes(self):
        sh = {x["name"]: x for x in self.gv["shareholders"]}
        self.assertNotIn("계", sh)
        self.assertEqual(sh["박예시"]["change"], "전량 처분")
        self.assertEqual(sh["박예시"]["endShares"], 0)
        self.assertEqual(sh["김샘플"]["change"], "증가")
        self.assertEqual(sh["김샘플"]["deltaPct"], 0.65)
        self.assertEqual(sh["샘플홀딩스㈜"]["change"], "변동 없음")

    def test_executive_changes(self):
        ex = {x["name"]: x for x in self.gv["executives"]}
        self.assertEqual(ex["최모의"]["change"], "신규 선임")
        self.assertEqual(ex["한이전"]["change"], "퇴임")
        self.assertEqual(ex["김샘플"]["change"], "유지")
        self.assertTrue(ex["정테스트"]["registered"])
        self.assertFalse(ex["정테스트"]["fullTime"])

    def test_investments_and_graph(self):
        inv = {x["name"]: x for x in self.gv["investments"]}
        self.assertNotIn("합 계", inv)
        self.assertEqual(inv["샘플LFP㈜"]["change"], "신규")
        self.assertEqual(inv["피어기업12(가상)"]["change"], "변동 없음")
        self.assertEqual(inv["피어기업12(가상)"]["corpCode"], "00888012")
        node = next(n for n in self.gv["graph"]["nodes"] if n["label"] == "피어기업12(가상)")
        self.assertEqual((node["kind"], node["corpCode"]), ("investee", "00888012"))
        ids = {n["id"] for n in self.gv["graph"]["nodes"]}
        self.assertTrue(all(e["from"] in ids and e["to"] in ids for e in self.gv["graph"]["edges"]))
        kinds = {c["kind"] for c in self.gv["changes"]}
        self.assertEqual(kinds, {"주주", "임원", "출자"})
        self.assertEqual(self.gv["priorRceptNo"], OLD)


class StepwiseTest(unittest.TestCase):
    def test_node_by_node_matches_graph(self):
        os.environ["RADAR_GRAPH"] = "builtin"
        try:
            ctx = g.prepare_context(settings(tempfile.mkdtemp()), dict(REQ))
            st = g.initial_state(ctx, dict(REQ))
            for fn in (g.ingest, g.numbers, g.diff):
                st = g.apply(st, fn)
            while True:
                st = g.apply(st, g.relate)
                st = g.apply(st, g.verify)
                if g.route_after_verify(st) == "report":
                    break
            rep = g.finalize(g.apply(st, g.report))
        finally:
            os.environ.pop("RADAR_GRAPH", None)
        self.assertEqual([t["node"] for t in rep["timeline"]], ["ingest", "numbers", "diff", "relate", "verify", "report"])
        self.assertEqual(rep["business"]["summary"]["failed"], 1)
        self.assertIsNotNone(rep["valuation"])


if __name__ == "__main__":
    unittest.main()
