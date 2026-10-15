"""명령줄 진입점.

  python -m radar demo              샘플(가상 기업)로 분석 → out/report.json
  python -m radar demo --fault      시연용 수치 오류를 주입해 검증 반려 루프를 보여 줌
  python -m radar run --company 999001 --year 2025 --reprt 11011 [--source service]
  python -m radar parse 원문.zip --rcept-no 20250311001085            W1 파싱 스파이크용: 원문 구조·함정 통계
  python -m radar schema             리포트 JSON Schema 출력

--source service(또는 RADAR_SOURCE=service)면 Spring 내부 데이터 API(docs/CONTRACT.md §11.2)로 실데이터를 받는다.
기업 목록·시장 화면·일일 수집(OpenDART·공공데이터포털)은 Spring(backend)이 맡는다 — 여기에는 없다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from radar.config import ROOT, Settings


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
    r.add_argument("--source", choices=["sample", "service"], help="service = Spring 내부 데이터 API(실데이터)")
    r.add_argument("--out", type=Path, default=ROOT / "out")
    ps = sub.add_parser("parse", help="원문 ZIP 하나를 파싱해 통계 출력(W1 스파이크)")
    ps.add_argument("zip", type=Path)
    ps.add_argument("--rcept-no", help="접수번호(생략 시 파일명에서)")
    ps.add_argument("--blocks", action="store_true", help="문단·표 목록까지 출력")
    sub.add_parser("schema", help="리포트 JSON Schema")
    a = p.parse_args(argv)

    if a.cmd in ("demo", "run"):
        from radar.pipeline.run import run_analysis

        s = Settings()
        if a.cmd == "demo":
            s.source = "sample"
            if not (s.sample_dir / "list.json").exists():
                import runpy
                runpy.run_path(str(ROOT.parent / "samples" / "build_samples.py"), run_name="__main__")
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
        from radar.parsing.parser import parse_filing_zip

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
        from radar.pipeline.schemas import Report

        print(json.dumps(Report.model_json_schema(), ensure_ascii=False, indent=1))
        return 0
    return 1
