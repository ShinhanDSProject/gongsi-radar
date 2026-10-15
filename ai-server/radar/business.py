"""사업 지표: 부문 매출·수주·생산능력·가동률 (docs/CONTRACT.md §6.3).

LLM을 쓰지 않는다. 머리글만 보고 종류를 알 수 있는 '구조가 명확한 표'만 규칙으로 읽고, 산술 검산을 붙인다.
  부문 매출       비중 합계≈100%, 표기 비중↔계산 비중 ±0.15%p, 표 합계↔재무 API 매출 ±0.5%(아니면 warn: 연결조정 차이 가능)
  수주           수주총액 = 기납품액 + 수주잔고(행마다), 잔고 합계↔본문 '수주잔고는 약 N억원'
  생산능력·가동률  단위가 같을 때만 합계, 합계↔본문 '생산능력 N톤', 가동률 0~100% 밖이면 warn, 가중평균 가동률
검산 통과 행만 신뢰하고, 불일치 행은 숫자를 그대로 보여 주되 '검산 불일치'로 표시한다(값을 고치지 않음).
"""
from __future__ import annotations

import re

from .formula import formula, inp, src
from .parser import Block, ParsedDoc
from .textutil import norm_ws, parse_krw
from .verify import check

KINDS = ("부문 매출", "수주", "생산능력·가동률")
_TOTAL_ROWS = {"합계", "계", "총계", "소계", "합 계"}
_UNIT_MULT = {"백만원": 1e6, "천원": 1e3, "억원": 1e8, "원": 1.0}
_BACKLOG_RE = re.compile(r"수주잔고는\s*(?:약\s*)?([\d,.]+\s*조\s*)?([\d,.]+\s*억\s*)?원")
_CAPA_RE = re.compile(r"생산능력[^.]*?([\d,]+(?:\.\d+)?)\s*톤")
NOTE = ("머리글로 종류를 알 수 있는 표만 규칙으로 읽었습니다(LLM 추출 없음). 검산 통과 행만 신뢰하고, "
        "검산 불일치 행은 원문 표를 직접 확인해야 합니다.")


def _k(s: str) -> str:
    return norm_ws(s).replace(" ", "")


def num(s: str | None) -> float | None:
    """'1,050,000' → 1050000, '80.2%' → 80.2, '-'·빈칸 → None (0으로 바꾸지 않음)."""
    if s is None:
        return None
    t = _k(s).replace(",", "").rstrip("%")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if t in ("", "-", "−"):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    v = -v if neg else v
    return int(v) if v == int(v) and "." not in t else v


def _unit_of(table: Block) -> tuple[str | None, float | None]:
    u = table.unit or ""
    for name, mult in _UNIT_MULT.items():
        if name in u:
            return name, mult
    return None, None


def _col(header: list[str], *needles: str) -> int | None:
    for i, h in enumerate(header):
        if i and all(n in _k(h) for n in needles):
            return i
    return None


def classify(table: Block) -> str | None:
    """구조가 명확한 표만 종류를 돌려준다. 행 길이가 머리글과 다르면 None."""
    h = table.header or []
    if len(h) < 3 or not table.rows or any(len(r) != len(h) for r in table.rows):
        return None
    if _col(h, "수주총액") and _col(h, "기납품") and _col(h, "수주잔고"):
        return "수주"
    if _col(h, "생산능력") and _col(h, "가동률"):
        return "생산능력·가동률"
    if _col(h, "매출") and _col(h, "비중"):
        return "부문 매출"
    return None


def find_tables(doc: ParsedDoc | None) -> dict[str, Block]:
    """종류별 첫 표(II. 사업의 내용 우선)."""
    out: dict[str, Block] = {}
    if doc is None:
        return out
    tables = sorted(doc.tables(), key=lambda b: (not b.section_key.startswith("II"), b.order))
    for t in tables:
        k = classify(t)
        if k and k not in out:
            out[k] = t
    return out


def _rows(table: Block | None) -> tuple[dict[str, list[str]], list[str] | None]:
    """(항목명 → 행, 합계 행)."""
    if table is None:
        return {}, None
    body, total = {}, None
    for r in table.rows or []:
        if _k(r[0]) in {_k(x) for x in _TOTAL_ROWS}:
            total = r
        else:
            body[r[0]] = r
    return body, total


def _yoy(p, c) -> float | None:
    if p is None or c is None or p == 0:
        return None
    return round((c - p) / abs(p) * 100, 2)


def _tsrc(doc: ParsedDoc, t: Block, what: str) -> dict:
    return src("원문 표", f"{t.section_path} · {what}", rcept_no=doc.rcept_no, pid=t.id)


def _status(checks: list[dict]) -> str:
    st = {c["status"] for c in checks}
    if "fail" in st:
        return "검산 불일치"
    if st == {"pass"}:
        return "검산 통과"
    return "검산 불가"


def _paragraph_value(doc: ParsedDoc, rx: re.Pattern, krw: bool) -> tuple[float | None, Block | None]:
    for b in doc.paragraphs():
        m = rx.search(b.text)
        if not m:
            continue
        if krw:
            vals = parse_krw(m.group(0))
            if vals:
                return vals[0][1], b
        else:
            return float(m.group(1).replace(",", "")), b
    return None, None


# ---- 종류별 ---------------------------------------------------------------------
def _segment(side_docs, side_tables, labels, years, revenue) -> tuple[list, list, list]:
    rows_out, checks, formulas = [], [], []
    per_side = {}
    for side in ("prior", "current"):
        t = side_tables.get(side)
        if t is None:
            continue
        h = t.header
        ai, si = _col(h, "매출"), _col(h, "비중")
        body, _ = _rows(t)
        amts = {lab: num(r[ai]) for lab, r in body.items()}
        shares = {lab: num(r[si]) for lab, r in body.items()}
        known = [v for v in amts.values() if v is not None]
        total = sum(known) if len(known) == len(amts) else None
        per_side[side] = (t, ai, si, amts, shares, total)
        y = years[side]
        doc = side_docs[side]
        unit, mult = _unit_of(t)
        share_vals = [v for v in shares.values() if v is not None]
        if share_vals:
            ssum = sum(share_vals)
            checks.append(check(f"비중 합계({y})", abs(ssum - 100) <= 0.5, f"표기 비중 합계 {ssum:.1f}%"))
        rev = revenue.get(side)
        f_in = [inp(lab, v, unit or "", _tsrc(doc, t, f"{lab} {h[ai]}")) for lab, v in amts.items()]
        formulas.append(formula(f"segment_total_{y}", f"부문 매출 합계({y})", " + ".join(amts) or "합계",
                                f_in, total, unit or "", reason=None if total is not None else "빈 칸이 있어 합계를 내지 않음"))
        if total is not None and mult and rev:
            diff = (total * mult - rev) / abs(rev) * 100
            ok = abs(diff) <= 0.5
            checks.append(check(f"표 합계↔재무 API 매출({y})", True if ok else None,
                                f"표 {total:,.0f}{unit} vs 재무 API {rev / mult:,.0f}{unit} (차이 {diff:+.2f}%)"
                                + ("" if ok else " — 연결조정 차이 가능")))
            formulas.append(formula(f"segment_vs_revenue_{y}", f"부문 합계와 재무 API 매출 차이({y})",
                                    "(표 합계 × 단위 − 재무 API 매출) ÷ 재무 API 매출 × 100",
                                    [inp("표 합계", total * mult, "원", _tsrc(doc, t, "합계")),
                                     inp("재무 API 매출", rev, "원", src("재무 API", f"{y} 매출액"))], diff, "%", digits=2))
        elif total is not None:
            checks.append(check(f"표 합계↔재무 API 매출({y})", None, "단위 또는 재무 API 매출이 없어 대조하지 않음"))
    for lab in labels:
        vals_a, vals_s, rchecks = {}, {}, []
        for side in ("prior", "current"):
            if side not in per_side:
                continue
            t, ai, si, amts, shares, total = per_side[side]
            a, s = amts.get(lab), shares.get(lab)
            vals_a[side], vals_s[side] = a, s
            if lab in amts:
                if a is not None and s is not None and total:
                    calc = a / total * 100
                    rchecks.append(check(f"표기 비중↔계산 비중({years[side]})", abs(calc - s) <= 0.15,
                                         f"표기 {s:.1f}% vs 계산 {calc:.2f}%"))
                else:
                    rchecks.append(check(f"표기 비중↔계산 비중({years[side]})", None, "빈 칸이 있어 계산하지 않음"))
        unit = next((_unit_of(per_side[s][0])[0] for s in per_side), None)
        rows_out.append({"label": lab, "status": _status(rchecks), "checks": rchecks, "values": [
            {"name": "매출액", "unit": unit or "", "prior": vals_a.get("prior"), "current": vals_a.get("current"),
             "yoyPct": _yoy(vals_a.get("prior"), vals_a.get("current"))},
            {"name": "비중", "unit": "%", "prior": vals_s.get("prior"), "current": vals_s.get("current"), "yoyPct": None}]})
    return rows_out, checks, formulas


def _orders(side_docs, side_tables, labels, years) -> tuple[list, list, list]:
    rows_out, checks, formulas = [], [], []
    per_side = {}
    for side in ("prior", "current"):
        t = side_tables.get(side)
        if t is None:
            continue
        h = t.header
        ci = (_col(h, "수주총액"), _col(h, "기납품"), _col(h, "수주잔고"))
        body, _ = _rows(t)
        vals = {lab: tuple(num(r[i]) for i in ci) for lab, r in body.items()}
        per_side[side] = (t, vals)
        y, doc = years[side], side_docs[side]
        unit, mult = _unit_of(t)
        backlog = [v[2] for v in vals.values()]
        total = sum(backlog) if None not in backlog else None
        formulas.append(formula(f"backlog_total_{y}", f"수주잔고 합계({y})", " + ".join(vals) or "합계",
                                [inp(lab, v[2], unit or "", _tsrc(doc, t, f"{lab} 수주잔고")) for lab, v in vals.items()],
                                total, unit or "", reason=None if total is not None else "빈 칸이 있어 합계를 내지 않음",
                                notes=["검산 불일치 행도 표에 적힌 값 그대로 더함"]))
        stated, para = _paragraph_value(doc, _BACKLOG_RE, krw=True)
        if stated is None:
            checks.append(check(f"수주잔고 합계↔본문({y})", None, "본문에 '수주잔고는 약 N억원' 서술이 없음"))
        elif total is None or not mult:
            checks.append(check(f"수주잔고 합계↔본문({y})", None, "표 합계 또는 단위가 없어 대조하지 않음"))
        else:
            ok = abs(total * mult - stated) <= max(1e8, abs(stated) * 0.005)
            checks.append(check(f"수주잔고 합계↔본문({y})", ok,
                                f"표 합계 {total:,.0f}{unit} vs 본문 {stated / mult:,.0f}{unit} ({para.id})"))
    for lab in labels:
        rchecks, v_tot, v_del, v_bl = [], {}, {}, {}
        for side in ("prior", "current"):
            if side not in per_side:
                continue
            t, vals = per_side[side]
            if lab not in vals:
                continue
            tot, dlv, bl = vals[lab]
            v_tot[side], v_del[side], v_bl[side] = tot, dlv, bl
            name = f"수주총액 = 기납품액 + 수주잔고({years[side]})"
            if None in (tot, dlv, bl):
                rchecks.append(check(name, None, "빈 칸이 있어 검산하지 않음"))
            else:
                ok = abs(dlv + bl - tot) <= max(1, abs(tot) * 0.001)
                rchecks.append(check(name, ok, f"기납품액 {dlv:,} + 수주잔고 {bl:,} = {dlv + bl:,}"
                                                 + (" = " if ok else " ≠ ") + f"수주총액 {tot:,}"))
        unit = next((_unit_of(per_side[s][0])[0] for s in per_side), None) or ""
        rows_out.append({"label": lab, "status": _status(rchecks), "checks": rchecks, "values": [
            {"name": n, "unit": unit, "prior": d.get("prior"), "current": d.get("current"),
             "yoyPct": _yoy(d.get("prior"), d.get("current"))}
            for n, d in (("수주총액", v_tot), ("기납품액", v_del), ("수주잔고", v_bl))]})
    return rows_out, checks, formulas


def _capacity(side_docs, side_tables, labels, years) -> tuple[list, list, list, str | None]:
    rows_out, checks, formulas = [], [], []
    per_side, units = {}, set()
    for side in ("prior", "current"):
        t = side_tables.get(side)
        if t is None:
            continue
        h = t.header
        ci, ri = _col(h, "생산능력"), _col(h, "가동률")
        m = re.search(r"\(([^)]+)\)", h[ci])
        units.add(m.group(1) if m else (_unit_of(t)[0] or None))
        body, _ = _rows(t)
        per_side[side] = (t, {lab: (num(r[ci]), num(r[ri])) for lab, r in body.items()}, h[ci], h[ri])
    unit = units.pop() if len(units) == 1 else None
    for side, (t, vals, hc, hr) in per_side.items():
        y, doc = years[side], side_docs[side]
        caps = [v[0] for v in vals.values()]
        if unit is None:
            checks.append(check(f"생산능력 합계({y})", None, "표 단위가 분명하지 않거나 서로 달라 합계를 내지 않음"))
            continue
        total = sum(caps) if None not in caps else None
        formulas.append(formula(f"capacity_total_{y}", f"생산능력 합계({y})", " + ".join(vals) or "합계",
                                [inp(lab, v[0], unit, _tsrc(doc, t, f"{lab} {hc}")) for lab, v in vals.items()],
                                total, unit, reason=None if total is not None else "빈 칸이 있어 합계를 내지 않음"))
        pairs = [(c, r) for c, r in vals.values() if c is not None and r is not None]
        wavg = sum(c * r for c, r in pairs) / sum(c for c, _ in pairs) if pairs and len(pairs) == len(vals) else None
        w_in = []
        for lab, (c, r) in vals.items():
            w_in += [inp(f"{lab} 생산능력", c, unit, _tsrc(doc, t, f"{lab} {hc}")),
                     inp(f"{lab} 가동률", r, "%", _tsrc(doc, t, f"{lab} {hr}"))]
        formulas.append(formula(f"utilization_wavg_{y}", f"가중평균 가동률({y})", "Σ(생산능력 × 가동률) ÷ Σ생산능력",
                                w_in, wavg, "%", digits=2,
                                reason=None if wavg is not None else "빈 칸이 있어 계산하지 않음"))
        stated, para = (_paragraph_value(doc, _CAPA_RE, krw=False) if unit == "톤" else (None, None))
        if stated is None:
            checks.append(check(f"생산능력 합계↔본문({y})", None, "본문에 '생산능력 N톤' 서술이 없음"))
        elif total is not None:
            checks.append(check(f"생산능력 합계↔본문({y})", abs(total - stated) <= max(1, stated * 0.005),
                                f"표 합계 {total:,.0f}{unit} vs 본문 {stated:,.0f}{unit} ({para.id})"))
    for lab in labels:
        rchecks, v_c, v_r = [], {}, {}
        for side, (t, vals, _, _) in per_side.items():
            if lab not in vals:
                continue
            c, r = vals[lab]
            v_c[side], v_r[side] = c, r
            name = f"가동률 0~100%({years[side]})"
            if r is None:
                rchecks.append(check(name, None, "가동률 빈 칸"))
            else:
                rchecks.append(check(name, True if 0 <= r <= 100 else None, f"{r:.1f}%"
                                     + ("" if 0 <= r <= 100 else " — 범위 밖, 원문 확인 필요")))
        rows_out.append({"label": lab, "status": _status(rchecks), "checks": rchecks, "values": [
            {"name": "생산능력", "unit": unit or "", "prior": v_c.get("prior"), "current": v_c.get("current"),
             "yoyPct": _yoy(v_c.get("prior"), v_c.get("current"))},
            {"name": "가동률", "unit": "%", "prior": v_r.get("prior"), "current": v_r.get("current"), "yoyPct": None}]})
    return rows_out, checks, formulas, unit


# ---- 진입점 ---------------------------------------------------------------------
def extract_business(prior_doc: ParsedDoc | None, cur_doc: ParsedDoc, revenue_by_year: dict | None = None,
                     years: tuple[int, int] | None = None) -> dict:
    """Business(§6.3). revenue_by_year: {"prior": 원, "current": 원} 또는 {연도: 원}(years를 줄 때).

    years=(전기 연도, 당기 연도)는 검산·계산식 이름에 쓴다. 없으면 '전기'·'당기'.
    """
    yrs = {"prior": years[0], "current": years[1]} if years else {"prior": "전기", "current": "당기"}
    rv = revenue_by_year or {}
    revenue = {side: rv.get(side, rv.get(yrs[side])) for side in ("prior", "current")}
    docs = {"prior": prior_doc, "current": cur_doc}
    found = {side: find_tables(d) for side, d in docs.items()}
    groups = []
    for kind in KINDS:
        tabs = {side: found[side].get(kind) for side in docs if found[side].get(kind) is not None}
        if not tabs:
            continue
        labels: list[str] = []
        for side in ("current", "prior"):  # 당기 순서 우선, 전기에만 있는 항목은 뒤에
            for lab in _rows(tabs.get(side))[0]:
                if lab not in labels:
                    labels.append(lab)
        unit = None
        if kind == "부문 매출":
            rows, checks, formulas = _segment(docs, tabs, labels, yrs, revenue)
            unit = next((_unit_of(t)[0] for t in tabs.values()), None)
        elif kind == "수주":
            rows, checks, formulas = _orders(docs, tabs, labels, yrs)
            unit = next((_unit_of(t)[0] for t in tabs.values()), None)
        else:
            rows, checks, formulas, unit = _capacity(docs, tabs, labels, yrs)
        t0 = tabs.get("current") or tabs.get("prior")
        groups.append({"kind": kind, "title": " / ".join(t0.header or []), "unit": unit,
                       "sectionPath": t0.section_path,
                       "priorPid": tabs["prior"].id if "prior" in tabs else None,
                       "currentPid": tabs["current"].id if "current" in tabs else None,
                       "checks": checks, "rows": rows, "formulas": formulas})
    rows = [r for g in groups for r in g["rows"]]
    summary = {"passed": sum(r["status"] == "검산 통과" for r in rows),
               "failed": sum(r["status"] == "검산 불일치" for r in rows),
               "unchecked": sum(r["status"] == "검산 불가" for r in rows)}
    note = NOTE if groups else "구조가 명확한 사업 지표 표(부문 매출·수주·생산능력)를 찾지 못했습니다."
    return {"groups": groups, "summary": summary, "note": note}
