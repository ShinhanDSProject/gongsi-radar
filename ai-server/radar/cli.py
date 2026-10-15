"""명령줄 진입점.

  python -m radar demo              샘플(가상 기업)로 분석 → out/report.json
  python -m radar demo --fault      시연용 수치 오류를 주입해 검증 반려 루프를 보여 줌
  python -m radar run --company 005930 --year 2025 --reprt 11011   (RADAR_SOURCE=opendart, OPENDART_API_KEY 필요)
  python -m radar parse 원문.zip --rcept-no 20250311001085            W1 파싱 스파이크용: 원문 구조·함정 통계
  python -m radar schema             리포트 JSON Schema 출력
  python -m radar companies [검색어]   기업 목록·검색(매출·영업이익률·시가총액·PER·PBR)
  python -m radar company 999001     기업 상세 요약(재무 다년·시장 지표·사업 지표·지배구조) --json 이면 전체 JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ROOT, Settings


def _write_outputs(rep: dict, out_dir: Path) -> None:
    # 리뷰 화면은 frontend/(React)로 옮겼다. 여기서는 계약 JSON만 쓴다
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n결과: {out_dir / 'report.json'}")


def _print_summary(rep: dict) -> None:
    m = rep["meta"]
    print(f"{m['company']['corp_name']} · {m['prior']['report_nm']} → {m['current']['report_nm']}"
          f" · 임베더 {m['embedder']} · LLM {m['llm']} · 그래프 {m['graph_engine']}")
    for t in rep["timeline"]:
        print(f"  {t['label']:<14} {t['ended_ms'] - t['started_ms']:>5}ms  {t['note']}")
    print("\n관련 서술")
    for r in rep["relations"]:
        print(f"  [{r['level']}·{r['verification']['status']}] {r['statement']}")
    print("\n변경 문단 상위 8건")
    for c in rep["changes"][:8]:
        print(f"  {c['id']} [{c['edit_type']}·{c['topic']}] {c['summary'][:90]}")


def _eok(won) -> str:
    return "-" if won is None else f"{won / 1e8:,.0f}억"


def _num(v, unit: str = "") -> str:
    return "-" if v is None else f"{v:,.2f}{unit}"


def _print_profile(prof: dict) -> None:
    c = prof["company"]
    print(f"{c['corpName']} ({c['stockCode']}, {c['corpCode']}) · {c['induty'] or '업종 정보 없음'}")
    fin = prof["financials"]
    print(f"\n재무 ({fin['fsDiv']}, 억원·%)  " + "  ".join(f"{y:>10}" for y in fin["columns"]))
    for r in fin["rows"]:
        vals = [(_num(v) if r["account"].endswith("(%)") else _eok(v)) for v in r["values"]]
        print(f"  {r['account']:<12}" + "  ".join(f"{v:>10}" for v in vals))
    v = prof["valuation"]
    print("\n시장 지표" + (f" (시세 {v['asOf']}, {v['marketSource']})" if v else f": {prof['valuationNote']}"))
    for m in (v or {}).get("metrics", []):
        val = _eok(m["result"]) if m["unit"] == "원" else _num(m["result"], m["unit"])
        print(f"  {m['label']:<18} {val:>12}  {m['expr']}" + (f"  [계산 안 함: {m['reason']}]" if m["status"] != "계산됨" else ""))
    b = prof["business"]
    if b:
        print(f"\n사업 지표 검산: 통과 {b['summary']['passed']} · 불일치 {b['summary']['failed']} · 불가 {b['summary']['unchecked']}")
        for g in b["groups"]:
            print(f"  [{g['kind']}] " + ", ".join(f"{r['label']}({r['status']})" for r in g["rows"]))
    g = prof["governance"]
    if g:
        print("\n지배구조 변동")
        for ch in g["changes"]:
            print(f"  [{ch['kind']}] {ch['text']}")
    print(f"\n공시 {len(prof['filings'])}건: " + ", ".join(f["reportNm"] for f in prof["filings"]))
    for n in prof["notes"]:
        print(f"  * {n}")


def _progress(e: dict) -> None:
    if e["type"] == "node_start":
        again = e["round"] and e["node"] in ("relate", "verify")
        print(f"  ▶ {e['label']}" + (f" ({e['round'] + 1}차)" if again else ""), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="공시레이더 프로토타입")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="샘플 데이터로 분석")
    d.add_argument("--fault", action="store_true", help="시연용 수치 오류 주입(반려 루프 확인)")
    d.add_argument("--out", type=Path, default=ROOT / "out")
    r = sub.add_parser("run", help="회사·연도 지정 분석")
    r.add_argument("--company", required=True)
    r.add_argument("--year", type=int, required=True)
    r.add_argument("--reprt", default="11011", choices=["11011", "11012", "11013", "11014"])
    r.add_argument("--source", choices=["sample", "opendart"])
    r.add_argument("--out", type=Path, default=ROOT / "out")
    ps = sub.add_parser("parse", help="원문 ZIP 하나를 파싱해 통계 출력(W1 스파이크)")
    ps.add_argument("zip", type=Path)
    ps.add_argument("--rcept-no", help="접수번호(생략 시 파일명에서)")
    ps.add_argument("--blocks", action="store_true", help="문단·표 목록까지 출력")
    sub.add_parser("schema", help="리포트 JSON Schema")
    cs = sub.add_parser("companies", help="기업 목록·검색")
    cs.add_argument("q", nargs="?", default="")
    cs.add_argument("--limit", type=int, default=50)
    cs.add_argument("--source", choices=["sample", "opendart"])
    cp = sub.add_parser("company", help="기업 상세 요약")
    cp.add_argument("company", help="종목코드·고유번호·회사명")
    cp.add_argument("--json", action="store_true", help="CompanyProfile 전체 JSON 출력")
    cp.add_argument("--source", choices=["sample", "opendart"])
    a = p.parse_args(argv)

    if a.cmd in ("companies", "company"):
        from .sources import make_source

        s = Settings()
        if a.source:
            s.source = a.source
        src = make_source(s)
        if a.cmd == "companies":
            from .company import search_companies

            for r in search_companies(src, a.q, a.limit):
                print(f"{r['stockCode']:<7} {r['corpName']:<16} 매출 {_eok(r['revenue']):>10} 영업이익률 {_num(r['opMarginPct'], '%'):>7}"
                      f" 시총 {_eok(r['marketCap']):>10} PER {_num(r['per']):>7} PBR {_num(r['pbr']):>5}  {r['basis'] or ''}")
            return 0
        from .company import company_profile

        prof = company_profile(src, src.resolve(a.company)["corp_code"])
        if a.json:
            print(json.dumps(prof, ensure_ascii=False, indent=1))
        else:
            _print_profile(prof)
        return 0

    if a.cmd in ("demo", "run"):
        from .service import run_analysis

        s = Settings()
        if a.cmd == "demo":
            s.source = "sample"
            if not (s.sample_dir / "list.json").exists():
                import runpy
                runpy.run_path(str(ROOT / "samples" / "build_samples.py"), run_name="__main__")
            req = {"company": "999001", "bsns_year": 2025, "reprt_code": "11011", "demo_fault_injection": a.fault}
        else:
            if a.source:
                s.source = a.source
            req = {"company": a.company, "bsns_year": a.year, "reprt_code": a.reprt}
        rep = run_analysis(req, s, on_event=_progress)
        _print_summary(rep)
        _write_outputs(rep, a.out)
        return 0

    if a.cmd == "parse":
        from .parser import parse_filing_zip

        rno = a.rcept_no or a.zip.stem
        doc = parse_filing_zip(a.zip.read_bytes(), rno)
        print(json.dumps(doc.stats(), ensure_ascii=False, indent=1))
        for sec in doc.sections:
            n_p, n_t = len(doc.paragraphs(sec.key)), len(doc.tables(sec.key))
            print(f"  {sec.key:<8} 문단 {n_p:>3} 표 {n_t:>2}  {sec.path}")
            if a.blocks:
                for b in doc.blocks:
                    if b.section_key == sec.key:
                        print(f"      {b.id}  {b.text[:80]}")
        return 0


    if a.cmd == "schema":
        from .schemas import Report

        print(json.dumps(Report.model_json_schema(), ensure_ascii=False, indent=1))
        return 0
    return 1
