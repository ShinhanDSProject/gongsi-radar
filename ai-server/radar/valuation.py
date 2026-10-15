"""시장 지표: 시가총액·TTM·PER·PBR (알파인더 규칙, docs/CONTRACT.md §6.5).

  TTM = 최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적 (같은 연결·별도 범위)
  PER = 시가총액 ÷ 지배주주 순이익 (TTM, 연간 두 가지). 이익 ≤ 0이면 계산 안 함
  PBR = 시가총액 ÷ 최근 기말 지배주주 자본. 자본 ≤ 0이면 계산 안 함
  지배주주 계정이 없으면 전체 계정(당기순이익·자본총계)으로 대체하고 입력값 note에 '대체 계정'을 남긴다.

수집(gather_valuation_inputs)과 계산(valuation_from_inputs)을 나눴다. 파이프라인은 ingest에서 수집하고
numbers에서 계산한다. 한 번에 부를 때는 compute_valuation. 판단 문구는 만들지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime

from .financials import amount
from .formula import fin_source, formula, inp, ratio, src
from .sources import REPRT, SourceError, data_origin

INTERIM_ORDER = ("11014", "11012", "11013")  # 3분기 → 반기 → 1분기: 가장 최근 누적부터
FLOW, STOCK = ("IS", "CIS"), ("BS",)

# key: (재무제표 구분, 표준계정 ID, 계정명 후보)
ACCOUNTS = {
    "rev": (FLOW, ("ifrs-full_Revenue",), ("매출액", "수익(매출액)", "영업수익")),
    "op": (FLOW, ("dart_OperatingIncomeLoss",), ("영업이익", "영업이익(손실)")),
    "ni": (FLOW, ("ifrs-full_ProfitLoss",), ("당기순이익", "당기순이익(손실)")),
    "ni_owner": (FLOW, ("ifrs-full_ProfitLossAttributableToOwnersOfParent",),
                 ("지배기업의 소유주에게 귀속되는 당기순이익", "지배기업의 소유주에게 귀속되는 당기순이익(손실)",
                  "지배기업 소유주지분", "지배기업의 소유주지분", "지배기업소유주지분순이익")),
    "assets": (STOCK, ("ifrs-full_Assets",), ("자산총계",)),
    "liab": (STOCK, ("ifrs-full_Liabilities",), ("부채총계",)),
    "equity": (STOCK, ("ifrs-full_Equity",), ("자본총계",)),
    "equity_owner": (STOCK, ("ifrs-full_EquityAttributableToOwnersOfParent",),
                     ("지배기업의 소유주에게 귀속되는 자본", "지배기업 소유주지분", "지배기업의 소유주지분")),
}
FALLBACK = {"ni_owner": "ni", "equity_owner": "equity"}
NAMES = {"rev": "매출액", "op": "영업이익", "ni": "당기순이익", "ni_owner": "지배주주 순이익",
         "equity": "자본총계", "equity_owner": "지배주주 자본", "assets": "자산총계", "liab": "부채총계"}


def _nm(s: str) -> str:
    return "".join((s or "").split())


def find_row(rows: list[dict], key: str) -> dict | None:
    """표준계정 ID 우선, 없으면 계정명(공백 무시)으로. 다중회사 주요계정 행은 account_id가 없다."""
    sjs, ids, names = ACCOUNTS[key]
    cands = [r for r in rows if (r.get("sj_div") or "") in sjs]
    for r in cands:
        if r.get("account_id") in ids:
            return r
    wanted = {_nm(n) for n in names}
    return next((r for r in cands if _nm(r.get("account_nm")) in wanted), None)


def pick(rows: list[dict], key: str) -> tuple[dict | None, bool]:
    """(행, 대체 계정 여부)."""
    r = find_row(rows, key)
    if r is None and key in FALLBACK:
        return find_row(rows, FALLBACK[key]), True
    return r, False


def _as_of(v) -> date:
    if v is None:
        return date.today()
    if isinstance(v, date):
        return v
    s = str(v).replace("-", "")
    return datetime.strptime(s[:8], "%Y%m%d").date()


def _filed_by(rows: list[dict], as_of: date) -> bool:
    """접수번호 앞 8자리(접수일)가 기준일 이전인지. 접수번호가 없으면(피어 주요계정) 확인하지 않는다."""
    rno = next((r.get("rcept_no") for r in rows if r.get("rcept_no")), None)
    return not rno or rno[:8] <= as_of.strftime("%Y%m%d")


def _rcept(rows: list[dict]) -> str:
    return next((r.get("rcept_no") for r in rows if r.get("rcept_no")), "") or ""


# ---- 수집 ------------------------------------------------------------------------
def gather_valuation_inputs(source, company: dict, as_of=None) -> dict:
    """시장 지표에 필요한 원자료: 최근 연간 재무, 그다음 해 최근 중간 재무, 시세. 실패는 notes로 남긴다."""
    d = _as_of(as_of)
    corp = company["corp_code"]
    notes: list[str] = []
    annual = None
    for y in range(d.year - 1, d.year - 5, -1):  # 기준일 전년부터 거슬러 올라가며 사업보고서 재무를 찾는다
        try:
            rows, fs = source.financials(corp, y, "11011")
        except SourceError:
            continue
        if _filed_by(rows, d):
            annual = {"year": y, "rows": rows, "fs": fs, "rcept_no": _rcept(rows)}
            break
    interim = None
    if annual:
        for code in INTERIM_ORDER:
            try:
                rows, fs = source.financials(corp, annual["year"] + 1, code)
            except SourceError:
                continue
            if not _filed_by(rows, d):
                continue
            if fs != annual["fs"]:
                notes.append(f"{annual['year'] + 1} {REPRT[code]['name']} 재무가 {fs}라 연간({annual['fs']})과 범위가 달라 TTM에 쓰지 않음")
                continue
            interim = {"year": annual["year"] + 1, "reprt_code": code, "rows": rows, "fs": fs, "rcept_no": _rcept(rows)}
            break
    else:
        notes.append("기준일 이전 사업보고서 재무 데이터를 찾지 못함")
    try:
        prices = [p for p in source.market(company.get("stock_code") or "") if p.get("basDt", "") <= d.strftime("%Y%m%d")]
    except SourceError as e:
        prices = []
        notes.append(f"시세 조회 실패: {e}")
    if not prices:
        notes.append("시세 없음(공공데이터포털 키 미설정이거나 해당 종목 시세 없음)")
    msrc = None
    if prices:
        msrc = "sample" if data_origin(source) == "sample" else "data.go.kr"
    return {"company": company, "as_of": d.isoformat(), "annual": annual, "interim": interim,
            "prices": sorted(prices, key=lambda p: p["basDt"]), "market_source": msrc, "notes": notes}


# ---- 계산 ------------------------------------------------------------------------
def _cum(row: dict | None, reprt_code: str, current: bool) -> tuple[int | None, str]:
    """중간보고서 손익의 누적 금액과 쓴 필드. 1분기는 3개월이 곧 누적이라 누적 필드가 비어 있을 수 있다."""
    if row is None:
        return None, ""
    f_add = "thstrm_add_amount" if current else "frmtrm_add_amount"
    v = amount(row.get(f_add))
    if v is not None:
        return v, f_add
    if reprt_code == "11013":
        for f in (("thstrm_amount",) if current else ("frmtrm_q_amount", "frmtrm_amount")):
            v = amount(row.get(f))
            if v is not None:
                return v, f
    return None, f_add


def _ttm(key: str, annual: dict, interim: dict | None) -> dict:
    """TTM Formula. 지배주주 계정은 연간·중간 양쪽에 다 있어야 쓰고, 아니면 둘 다 전체 계정으로 맞춘다."""
    nm = NAMES[key]
    use = key
    fallback = False
    if key in FALLBACK:
        has_a = find_row(annual["rows"], key) is not None
        has_i = interim is None or find_row(interim["rows"], key) is not None
        if not (has_a and has_i):
            use, fallback = FALLBACK[key], True
    note = f"대체 계정: 지배주주 계정이 없어 {NAMES[use]}(전체) 사용" if fallback else None
    a_row = find_row(annual["rows"], use)
    a_val = amount(a_row.get("thstrm_amount")) if a_row else None
    a_in = inp(f"최근 연간({annual['year']})", a_val, "원", fin_source(a_row, "thstrm_amount", fs_div=annual["fs"]), note)
    fid = {"rev": "ttm_revenue", "op": "ttm_op", "ni_owner": "ttm_ni_owner"}[key]
    if interim is None:
        return formula(fid, f"{nm} TTM", "최근 연간 (연간 이후 중간보고서 없음)", [a_in], a_val, "원",
                       reason=None if a_val is not None else f"연간 {nm} 값 없음",
                       notes=["연간 이후 중간보고서가 없어 최근 연간 값을 그대로 씀"] + ([note] if note else []))
    code = interim["reprt_code"]
    i_row = find_row(interim["rows"], use)
    c_val, c_f = _cum(i_row, code, True)
    p_val, p_f = _cum(i_row, code, False)
    rname = REPRT[code]["name"].replace("보고서", "")
    inputs = [a_in,
              inp(f"당해 {rname} 누적({interim['year']})", c_val, "원", fin_source(i_row, c_f, fs_div=interim["fs"]), note),
              inp(f"전년 같은 {rname} 누적({interim['year'] - 1})", p_val, "원", fin_source(i_row, p_f, fs_div=interim["fs"]), note)]
    res = None if None in (a_val, c_val, p_val) else a_val + c_val - p_val
    return formula(fid, f"{nm} TTM", "최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적", inputs, res, "원",
                   notes=[f"범위: {interim['fs']}(연간·중간 같은 범위)"] + ([note] if note else []))


def _inputs_of(f: dict) -> list[dict]:
    """다른 Formula의 결과를 다음 계산의 입력값으로."""
    return [inp(f["label"], f["result"], f["unit"], src("계산", f"{f['label']} = {f['expr']}"))]


def valuation_from_inputs(vi: dict) -> dict | None:
    """Valuation(§6.5). 연간 재무가 없으면 None."""
    annual, interim = vi.get("annual"), vi.get("interim")
    if not annual:
        return None
    notes = list(vi.get("notes") or [])
    prices = vi.get("prices") or []
    last = prices[-1] if prices else None
    price = None
    if last:
        close, shares = amount(last.get("clpr")), amount(last.get("lstgStCnt"))
        cap = close * shares if close is not None and shares is not None else None
        price = {"basDt": last["basDt"], "close": close, "listedShares": shares, "marketCap": cap}
        p_src = src("시세", f"{last.get('itmsNm', '')} {last['basDt']} 종가".strip(), field="clpr")
        s_src = src("시세", f"{last.get('itmsNm', '')} {last['basDt']} 상장주식수".strip(), field="lstgStCnt")
        mc = formula("market_cap", "시가총액", "종가 × 상장주식수",
                     [inp("종가", close, "원", p_src), inp("상장주식수", shares, "주", s_src)], cap, "원",
                     notes=[f"기준일 {last['basDt']}"])
    else:
        mc = formula("market_cap", "시가총액", "종가 × 상장주식수",
                     [inp("종가", None, "원"), inp("상장주식수", None, "주")], None, "원", reason="시세 없음")
    t_rev, t_op, t_ni = _ttm("rev", annual, interim), _ttm("op", annual, interim), _ttm("ni_owner", annual, interim)

    def per(fid: str, label: str, earn_in: dict) -> dict:
        ins = _inputs_of(mc) + [earn_in]
        e = earn_in["value"]
        if e is not None and e <= 0:
            return formula(fid, label, "시가총액 ÷ 지배주주 순이익", ins, None, "배",
                           reason="지배주주 순이익이 0 이하라 PER을 계산하지 않음")
        return formula(fid, label, "시가총액 ÷ 지배주주 순이익", ins, ratio(mc["result"], e), "배", digits=2)

    t_note = next((n for n in t_ni["notes"] if n.startswith("대체 계정")), None)
    per_ttm = per("per_ttm", "PER(TTM)",
                  inp(t_ni["label"], t_ni["result"], "원", src("계산", f"{t_ni['label']} = {t_ni['expr']}"), t_note))
    a_row, a_fb = pick(annual["rows"], "ni_owner")
    a_ni = amount(a_row.get("thstrm_amount")) if a_row else None
    a_note = f"대체 계정: 지배주주 계정이 없어 {NAMES['ni']}(전체) 사용" if a_fb else None
    per_annual = per("per_annual", f"PER(연간 {annual['year']})",
                     inp(f"지배주주 순이익({annual['year']})", a_ni, "원",
                         fin_source(a_row, "thstrm_amount", fs_div=annual["fs"]), a_note))

    # PBR: 가장 최근 기말(중간보고서가 있으면 그 기말) 지배주주 자본
    base = interim or annual
    e_row, e_fb = pick(base["rows"], "equity_owner")
    eq = amount(e_row.get("thstrm_amount")) if e_row else None
    e_note = f"대체 계정: 지배주주 계정이 없어 {NAMES['equity']}(전체) 사용" if e_fb else None
    period = f"{base['year']} " + (f"{REPRT[base['reprt_code']]['name'].replace('보고서', '')}말" if interim else "기말")
    pbr_in = _inputs_of(mc) + [inp(f"지배주주 자본({period})", eq, "원", fin_source(e_row, "thstrm_amount", fs_div=base["fs"]), e_note)]
    if eq is not None and eq <= 0:
        pbr = formula("pbr", "PBR", "시가총액 ÷ 지배주주 자본", pbr_in, None, "배", reason="지배주주 자본이 0 이하라 PBR을 계산하지 않음")
    else:
        pbr = formula("pbr", "PBR", "시가총액 ÷ 지배주주 자본", pbr_in, ratio(mc["result"], eq), "배", digits=2)

    notes.append("PER·PBR은 계산식과 입력값만 보여 주며 해석하지 않습니다.")
    if not interim:
        notes.append(f"{annual['year'] + 1}년 중간보고서 재무가 없어 TTM은 {annual['year']}년 연간 값과 같음")
    return {
        "asOf": f"{last['basDt'][:4]}-{last['basDt'][4:6]}-{last['basDt'][6:]}" if last else None,
        "marketSource": vi.get("market_source"), "fsDiv": annual["fs"],
        "annual": {"year": annual["year"], "rceptNo": annual["rcept_no"]},
        "interim": ({"year": interim["year"], "reprtCode": interim["reprt_code"], "rceptNo": interim["rcept_no"]}
                    if interim else None),
        "price": price,
        "prices": [{"d": p["basDt"], "c": amount(p.get("clpr"))} for p in prices if amount(p.get("clpr")) is not None],
        "metrics": [mc, t_rev, t_op, t_ni, per_ttm, per_annual, pbr],
        "notes": notes,
    }


def compute_valuation(source, company: dict, as_of=None) -> dict | None:
    return valuation_from_inputs(gather_valuation_inputs(source, company, as_of))


def metric(val: dict | None, fid: str):
    """Valuation에서 지표 하나의 결과값(없으면 None)."""
    if not val:
        return None
    return next((m["result"] for m in val["metrics"] if m["id"] == fid), None)
