"""기업 목록·검색과 기업 상세(CompanyRow·CompanyProfile, docs/CONTRACT.md §6.6).

상세 = 재무 다년 표(계산식·출처 포함) + 시장 지표 + 사업 지표 + 지배구조 + 정기보고서 목록.
금액 단위는 원. 값이 없으면 None이고 계산식에 '계산 안 함' 사유가 붙는다.
AI 서버 Tool Gateway의 search_companies·get_company_profile이 이 두 함수를 부른다.
"""
from __future__ import annotations

from .business import extract_business
from .financials import amount
from .formula import fin_source, formula, inp, ratio, src
from .governance import build_governance, known_names
from .parser import ParseError, parse_filing_zip
from .sources import SourceError
from .valuation import find_row, gather_valuation_inputs, metric, valuation_from_inputs

PROFILE_ACCOUNTS = [("rev", "매출액"), ("op", "영업이익"), ("ni", "당기순이익"), ("ni_owner", "지배주주순이익"),
                    ("assets", "자산총계"), ("liab", "부채총계"), ("equity", "자본총계")]
_COLS = (("bfefrmtrm_amount", 2), ("frmtrm_amount", 1), ("thstrm_amount", 0))  # (필드, 기준 연도에서 뺄 해)
METRICS_LIMIT = 10  # OpenDART: 검색 결과가 이보다 많으면 지표를 계산하지 않는다(회사마다 API 여러 번)


def _match(c: dict, q: str) -> bool:
    if not q:
        return True
    q = q.strip().lower()
    return (q in (c.get("corp_name") or "").lower() or (c.get("stock_code") or "").startswith(q)
            or c.get("corp_code") == q)


def _row(c: dict) -> dict:
    return {"corpCode": c["corp_code"], "corpName": c["corp_name"], "stockCode": c.get("stock_code") or "",
            "induty": c.get("induty"), "hasFilings": False, "revenue": None, "opIncome": None, "opMarginPct": None,
            "marketCap": None, "per": None, "pbr": None, "basis": None}


def company_row(source, c: dict, as_of=None) -> dict:
    """회사 한 곳의 목록 행(지표 포함)."""
    row = _row(c)
    try:
        row["hasFilings"] = bool(source.filings(c["corp_code"]))
    except SourceError:
        pass
    vi = gather_valuation_inputs(source, c, as_of)
    a = vi["annual"]
    if not a:
        row["basis"] = "재무 데이터 없음"
        return row
    rv, op = (find_row(a["rows"], k) for k in ("rev", "op"))
    row["revenue"] = amount(rv.get("thstrm_amount")) if rv else None
    row["opIncome"] = amount(op.get("thstrm_amount")) if op else None
    m = ratio(row["opIncome"], row["revenue"])
    row["opMarginPct"] = round(m * 100, 2) if m is not None else None
    val = valuation_from_inputs(vi)
    row["marketCap"], row["per"], row["pbr"] = metric(val, "market_cap"), metric(val, "per_ttm"), metric(val, "pbr")
    row["basis"] = (f"매출·영업이익 {a['year']} 사업보고서({a['fs']})"
                    + (f" · PER(TTM)·PBR 시세 {val['asOf']}" if val and val.get("asOf") else " · 시세 없음"))
    return row


def search_companies(source, q: str = "", limit: int = 50, with_metrics: bool | None = None, as_of=None) -> list[dict]:
    """CompanyRow[]. 이름 부분 일치·종목코드 앞자리·고유번호로 찾는다.

    with_metrics 기본값: 샘플은 항상, OpenDART는 결과가 METRICS_LIMIT개 이하일 때만 지표를 계산한다.
    지표를 계산하지 않은 행은 hasFilings를 상장사 기준 True로 두고 basis에 사유를 적는다.
    """
    corps = [c for c in source.companies() if _match(c, q)][:max(0, limit)]
    if with_metrics is None:
        with_metrics = getattr(source, "name", "") == "sample" or len(corps) <= METRICS_LIMIT
    if with_metrics:
        return [company_row(source, c, as_of) for c in corps]
    out = []
    for c in corps:
        r = _row(c)
        r["hasFilings"], r["basis"] = True, f"검색 결과가 {METRICS_LIMIT}개를 넘어 지표를 계산하지 않음(검색어를 좁히세요)"
        out.append(r)
    return out


def _financial_table(annual: dict | None) -> dict:
    if not annual:
        return {"fsDiv": None, "columns": [], "rows": []}
    y, rows, fs = annual["year"], annual["rows"], annual["fs"]
    cols = [(f, y - back) for f, back in _COLS
            if any(amount(r.get(f)) is not None for r in rows)]  # 전전기 칸이 비어 있으면 열을 뺀다
    table, vals = [], {}
    for key, label in PROFILE_ACCOUNTS:
        r = find_row(rows, key)
        values, fms = [], []
        for f, yr in cols:
            v = amount(r.get(f)) if r else None
            values.append(v)
            fms.append(formula(f"{key}_{yr}", f"{label}({yr})", "재무 API 값",
                               [inp(label, v, "원", fin_source(r, f, label=f"{yr} {label} ({fs})", fs_div=None))],
                               v, "원", reason=None if v is not None else
                               ("재무 API에 해당 계정 없음" if r is None else "해당 기간 값 없음")))
        vals[key] = values
        table.append({"account": label, "values": values, "formulas": fms})
    margins, fms = [], []
    for k, (f, yr) in enumerate(cols):
        op, rv = vals["op"][k], vals["rev"][k]
        m = ratio(op, rv)
        margins.append(round(m * 100, 2) if m is not None else None)
        fms.append(formula(f"op_margin_{yr}", f"영업이익률({yr})", "영업이익 ÷ 매출액 × 100",
                           [inp("영업이익", op, "원", src("계산", f"{yr} 영업이익")),
                            inp("매출액", rv, "원", src("계산", f"{yr} 매출액"))],
                           m * 100 if m is not None else None, "%", digits=2,
                           reason=None if m is not None else "영업이익 또는 매출액이 없거나 매출액이 0"))
    table.append({"account": "영업이익률(%)", "values": margins, "formulas": fms})
    return {"fsDiv": fs, "columns": [str(yr) for _, yr in cols], "rows": table}


def _doc(source, rcept_no: str):
    return parse_filing_zip(source.document(rcept_no), rcept_no)


def company_profile(source, corp_code: str, as_of=None, include_valuation: bool = True,
                    valuation_note: str | None = None) -> dict:
    """CompanyProfile. include_valuation=False면 시장 지표를 만들지 않고 valuationNote에 사유(권한 없음 등)를 남긴다."""
    corps = source.companies()
    c = next((x for x in corps if x["corp_code"] == corp_code), None) or source.resolve(corp_code)
    company = {"corpCode": c["corp_code"], "corpName": c["corp_name"], "stockCode": c.get("stock_code") or "",
               "induty": c.get("induty")}
    notes: list[str] = []
    try:
        filings = source.filings(c["corp_code"])
    except SourceError as e:
        filings = []
        notes.append(f"공시 목록 조회 실패: {e}")

    vi = gather_valuation_inputs(source, c, as_of)
    annual = vi["annual"]
    fin = _financial_table(annual)
    if not annual:
        notes.append("사업보고서 재무 데이터가 없어 재무 표를 만들지 못함")

    valuation = None
    if include_valuation:
        valuation = valuation_from_inputs(vi)
        if valuation is None:
            valuation_note = valuation_note or "연간 재무 데이터가 없어 시장 지표를 계산하지 않음"
    else:
        valuation_note = valuation_note or "시장 지표 조회 권한이 없어 표시하지 않음"

    # 사업 지표: 원문이 있는 최근 사업보고서 두 해
    business = None
    annual_docs = sorted([f for f in filings if f["reprt_code"] == "11011" and f["hasDocument"]],
                         key=lambda f: f["bsns_year"], reverse=True)
    if len(annual_docs) >= 2 and annual_docs[0]["bsns_year"] - annual_docs[1]["bsns_year"] == 1:
        cur_f, pr_f = annual_docs[0], annual_docs[1]
        try:
            rev = {}
            for f in (cur_f, pr_f):
                try:
                    rows, _ = source.financials(c["corp_code"], f["bsns_year"], "11011")
                    r = find_row(rows, "rev")
                    rev[f["bsns_year"]] = amount(r.get("thstrm_amount")) if r else None
                except SourceError:
                    rev[f["bsns_year"]] = None
            business = extract_business(_doc(source, pr_f["rcept_no"]), _doc(source, cur_f["rcept_no"]), rev,
                                        (pr_f["bsns_year"], cur_f["bsns_year"]))
        except (SourceError, ParseError) as e:
            notes.append(f"사업 지표: 원문을 읽지 못함({e})")
    else:
        notes.append("사업 지표: 원문이 있는 연속 두 해 사업보고서가 없어 만들지 않음")

    # 지배구조: 최근 사업보고서 연도와 그 전년
    governance = None
    known = known_names([x for x in corps if x["corp_code"] != c["corp_code"]])
    gyear = annual["year"] if annual else (annual_docs[0]["bsns_year"] if annual_docs else None)
    if gyear:
        try:
            cur_g = source.governance(c["corp_code"], gyear, "11011")
            try:
                pr_g = source.governance(c["corp_code"], gyear - 1, "11011")
            except SourceError:
                pr_g = None
            governance = build_governance(cur_g, pr_g, known, c)
        except SourceError as e:
            notes.append(f"지배구조: {e}")
    notes.append("금액 단위는 원입니다. 숫자마다 계산식·출처를 펼쳐 볼 수 있습니다.")
    filing_rows = [{"rceptNo": f["rcept_no"], "reportNm": f["report_nm"], "rceptDt": f["rcept_dt"],
                    "reprtCode": f["reprt_code"], "bsnsYear": f["bsns_year"], "hasDocument": f["hasDocument"]}
                   for f in filings]
    return {"company": company, "filings": filing_rows, "financials": fin, "valuation": valuation,
            "valuationNote": valuation_note if valuation is None else None,
            "business": business, "governance": governance, "notes": notes}
