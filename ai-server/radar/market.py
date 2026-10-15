"""시장 화면(알파인더 /market 참고): 지수 추이 · 시가총액 추이 · 업종 지도(KSIC) · 최근 정기보고서.

계약은 docs/CONTRACT.md §9 MarketOverview. 숫자는 전부 시세 행(getStockPriceInfo 모양)에서 코드로 더한다.

  - 시가총액 추이: 날짜별 추적 종목 시가총액(mrktTotAmt) 합계. 그 날 시세가 없는 종목은 빼지 않고 직전 값을 이어 쓴다
    (시세가 하루 빠졌다고 합계가 꺼지면 시장이 폭락한 것처럼 보인다)
  - 지수 추이: 공식 지수(공공데이터포털 지수시세) 키가 있으면 그 값을, 없으면 추적 종목 시가총액으로 만든
    **대체 지수**(기준일 = 1,000)를 쓰고 kind="proxy"로 분명히 표시한다. 대체 지수를 코스피라고 부르지 않는다
  - 업종 지도: KSIC 코드 앞 두 자리(중분류) → 대분류 문자. 면적 = 시가총액. 색은 등락률이 아니다
  - 기간 변화: 최신일에서 거꾸로 7일·1개월·1년 이내의 마지막 거래일과 비교. 그만큼 데이터가 없으면 계산하지 않는다
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable

from .financials import amount
from .formula import src
from .sources import SourceError, dart_url

MARKETS = (("ALL", "전체"), ("KOSPI", "유가"), ("KOSDAQ", "코스닥"), ("KONEX", "코넥스"))
PERIODS = (("1D", "전일", None), ("1W", "1주", 7), ("1M", "1개월", 31), ("1Y", "1년", 365))
RANGES = (("1Y", 360), ("3Y", 3 * 365 - 10), ("5Y", 5 * 365 - 10))
INDEX_NAMES = (("KOSPI", "코스피"), ("KOSDAQ", "코스닥"))
PROXY_BASE = 1000.0

# KSIC 11 대분류(중분류 범위)
KSIC_SECTIONS = (
    ("A", 1, 3, "농업, 임업 및 어업"), ("B", 5, 8, "광업"), ("C", 10, 34, "제조업"),
    ("D", 35, 35, "전기, 가스, 증기 및 공기조절 공급업"), ("E", 36, 39, "수도, 하수 및 폐기물 처리, 원료 재생업"),
    ("F", 41, 42, "건설업"), ("G", 45, 47, "도매 및 소매업"), ("H", 49, 52, "운수 및 창고업"),
    ("I", 55, 56, "숙박 및 음식점업"), ("J", 58, 63, "정보통신업"), ("K", 64, 66, "금융 및 보험업"),
    ("L", 68, 68, "부동산업"), ("M", 70, 73, "전문, 과학 및 기술 서비스업"),
    ("N", 74, 76, "사업시설 관리, 사업 지원 및 임대 서비스업"), ("O", 84, 84, "공공 행정, 국방 및 사회보장 행정"),
    ("P", 85, 85, "교육 서비스업"), ("Q", 86, 87, "보건업 및 사회복지 서비스업"),
    ("R", 90, 91, "예술, 스포츠 및 여가관련 서비스업"), ("S", 94, 96, "협회 및 단체, 수리 및 기타 개인 서비스업"),
    ("T", 97, 98, "가구 내 고용활동 및 달리 분류되지 않은 자가 소비 생산활동"), ("U", 99, 99, "국제 및 외국기관"),
)
KSIC_DIVISIONS = {
    "10": "식료품 제조업", "11": "음료 제조업", "12": "담배 제조업", "13": "섬유제품 제조업", "14": "의복 제조업",
    "15": "가죽·가방·신발 제조업", "16": "목재 및 나무제품 제조업", "17": "펄프·종이 제조업", "18": "인쇄 및 기록매체 복제업",
    "19": "코크스·석유정제품 제조업", "20": "화학물질 및 화학제품 제조업", "21": "의료용 물질 및 의약품 제조업",
    "22": "고무 및 플라스틱제품 제조업", "23": "비금속 광물제품 제조업", "24": "1차 금속 제조업", "25": "금속 가공제품 제조업",
    "26": "전자부품·컴퓨터·영상·음향·통신장비 제조업", "27": "의료·정밀·광학 기기 및 시계 제조업", "28": "전기장비 제조업",
    "29": "기타 기계 및 장비 제조업", "30": "자동차 및 트레일러 제조업", "31": "기타 운송장비 제조업", "32": "가구 제조업",
    "33": "기타 제품 제조업", "34": "산업용 기계 및 장비 수리업", "35": "전기, 가스, 증기 및 공기조절 공급업",
    "36": "수도업", "37": "하수·폐수 및 분뇨 처리업", "38": "폐기물 수집·처리 및 원료 재생업", "39": "환경 정화 및 복원업",
    "41": "종합 건설업", "42": "전문직별 공사업", "45": "자동차 및 부품 판매업", "46": "도매 및 상품 중개업",
    "47": "소매업(자동차 제외)", "49": "육상 운송 및 파이프라인 운송업", "50": "수상 운송업", "51": "항공 운송업",
    "52": "창고 및 운송관련 서비스업", "55": "숙박업", "56": "음식점 및 주점업", "58": "출판업",
    "59": "영상·오디오 기록물 제작 및 배급업", "60": "방송업", "61": "우편 및 통신업",
    "62": "컴퓨터 프로그래밍·시스템 통합 및 관리업", "63": "정보서비스업", "64": "금융업", "65": "보험 및 연금업",
    "66": "금융 및 보험관련 서비스업", "68": "부동산업", "70": "연구개발업", "71": "전문 서비스업",
    "72": "건축기술·엔지니어링 및 기타 과학기술 서비스업", "73": "기타 전문·과학 및 기술 서비스업",
    "74": "사업시설 관리 및 조경 서비스업", "75": "사업 지원 서비스업", "76": "임대업(부동산 제외)", "85": "교육 서비스업",
    "86": "보건업", "87": "사회복지 서비스업", "90": "창작·예술 및 여가관련 서비스업", "91": "스포츠 및 오락관련 서비스업",
}
UNKNOWN = ("?", "업종 미확인")
INDUTY_LOOKUP_LIMIT = 300      # 실데이터에서 업종 코드(company.json)를 불러올 상위 종목 수


def ksic_section(code: str | None) -> tuple[str, str]:
    """KSIC 코드 → (대분류 문자, 이름). 숫자 앞 두 자리(중분류)로 판정한다."""
    m = re.match(r"\s*(\d{2})", code or "")
    if not m:
        return UNKNOWN
    div = int(m.group(1))
    for letter, lo, hi, name in KSIC_SECTIONS:
        if lo <= div <= hi:
            return letter, name
    return UNKNOWN


def ksic_division(code: str | None) -> tuple[str, str]:
    m = re.match(r"\s*(\d{2})", code or "")
    if not m:
        return "??", UNKNOWN[1]
    return m.group(1), KSIC_DIVISIONS.get(m.group(1), f"중분류 {m.group(1)}")


def _iso(bas: str) -> str:
    return f"{bas[:4]}-{bas[4:6]}-{bas[6:]}"


def _cap(row: dict) -> int | None:
    cap = amount(row.get("mrktTotAmt"))
    if cap is None and amount(row.get("clpr")) and amount(row.get("lstgStCnt")):
        cap = amount(row["clpr"]) * amount(row["lstgStCnt"])
    return cap


# ---- 기간 변화 ---------------------------------------------------------------------------------
def period_changes(series: list[dict]) -> list[dict]:
    """series: [{d: 'YYYY-MM-DD', v}] 오래된 것 → 최신. delta 단위는 series 값 단위."""
    out = []
    if not series:
        return [{"period": p, "label": lab, "pct": None, "delta": None, "from": None, "to": None,
                 "reason": "데이터 없음"} for p, lab, _ in PERIODS]
    last = series[-1]
    to = date.fromisoformat(last["d"])
    for code, label, days in PERIODS:
        if days is None:
            base = series[-2] if len(series) >= 2 else None
        else:
            target = to - timedelta(days=days)
            base = next((p for p in reversed(series) if date.fromisoformat(p["d"]) <= target), None)
            # 목표일과 너무 멀리 떨어진 값(데이터 시작점이 목표보다 한참 뒤)은 쓰지 않는다
            if base and (date.fromisoformat(base["d"]) < target - timedelta(days=10)):
                base = None
        if not base or not base["v"]:
            out.append({"period": code, "label": label, "pct": None, "delta": None, "from": None, "to": last["d"],
                        "reason": "기간 데이터 부족"})
            continue
        delta = last["v"] - base["v"]
        out.append({"period": code, "label": label, "pct": round(delta / abs(base["v"]) * 100, 2),
                    "delta": round(delta, 2), "from": base["d"], "to": last["d"]})
    return out


def available_ranges(series: list[dict]) -> list[str]:
    if len(series) < 2:
        return []
    span = (date.fromisoformat(series[-1]["d"]) - date.fromisoformat(series[0]["d"])).days
    return [code for code, need in RANGES if span >= need] or ["1Y"]


# ---- 시가총액 ----------------------------------------------------------------------------------
def cap_series(history: dict[str, list[dict]], codes: Iterable[str]) -> list[dict]:
    """날짜별 시가총액 합계. 그 날 시세가 빠진 종목은 직전 값을 이어 쓴다(처음 나타나기 전 날짜는 0)."""
    codes = list(codes)
    by_code: dict[str, dict[str, int]] = {}
    days: set[str] = set()
    for c in codes:
        m = {}
        for r in history.get(c, []):
            v = _cap(r)
            if v is not None and r.get("basDt"):
                m[r["basDt"]] = v
        if m:
            by_code[c] = m
            days.update(m)
    last: dict[str, int] = {}
    out = []
    for d in sorted(days):
        for c, m in by_code.items():
            if d in m:
                last[c] = m[d]
        out.append({"d": _iso(d), "v": sum(last.values())})
    return out


def proxy_index(series: list[dict]) -> list[dict]:
    """시가총액 합계를 첫날 = 1,000으로 맞춘 대체 지수. 상장·상폐로 종목 구성이 바뀌면 왜곡된다(공식 지수는 이를 보정한다)."""
    if not series or not series[0]["v"]:
        return []
    base = series[0]["v"]
    return [{"d": p["d"], "v": round(p["v"] / base * PROXY_BASE, 2)} for p in series]


# ---- 업종 지도 ---------------------------------------------------------------------------------
def _node(nid: str, name: str, level: str, code: str | None) -> dict:
    return {"id": nid, "name": name, "level": level, "code": code, "value": 0, "count": 0, "share": 0.0, "children": []}


def sector_tree(items: list[dict]) -> dict:
    """items: [{corp_code, corp_name, stock_code, induty_code, cap}] → 대분류 → 중분류 → 기업 트리."""
    root = _node("root", "전체 업종", "root", None)
    sections: dict[str, dict] = {}
    for it in items:
        if not it["cap"]:
            continue
        letter, sname = ksic_section(it.get("induty_code"))
        sec = sections.setdefault(letter, _node(f"S-{letter}", f"{letter} {sname}" if letter != "?" else sname,
                                                "section", None if letter == "?" else letter))
        dcode, dname = ksic_division(it.get("induty_code"))
        div = next((d for d in sec["children"] if d["code"] == dcode), None)
        if div is None:
            div = _node(f"D-{dcode}", f"{dcode} {dname}" if dcode != "??" else dname, "division",
                        None if dcode == "??" else dcode)
            sec["children"].append(div)
        div["children"].append({"id": f"C-{it['corp_code']}", "name": it["corp_name"], "level": "company",
                                "code": it["stock_code"], "value": it["cap"], "count": 1, "share": 0.0,
                                "corpCode": it["corp_code"]})
    root["children"] = list(sections.values())

    def total(n: dict) -> None:
        if n["level"] == "company":
            return
        for c in n["children"]:
            total(c)
        n["value"] = sum(c["value"] for c in n["children"])
        n["count"] = sum(c["count"] for c in n["children"])
        n["children"].sort(key=lambda c: -c["value"])
        for c in n["children"]:
            c["share"] = round(c["value"] / n["value"] * 100, 2) if n["value"] else 0.0

    total(root)
    root["share"] = 100.0
    return root


# ---- 최근 정기보고서 ----------------------------------------------------------------------------
def recent_table(filings: list[dict], caps: dict[str, int], corp_market: dict[str, str | None],
                 market: str, limit: int = 30) -> list[dict]:
    out = []
    for f in filings:
        if market != "ALL" and corp_market.get(f["corp_code"]) != market:
            continue
        nm = f.get("report_nm", "")
        out.append({"rceptNo": f["rcept_no"], "rceptDt": _iso(f["rcept_dt"]), "corpCode": f["corp_code"],
                    "corpName": f.get("corp_name"), "stockCode": f.get("stock_code") or None, "reportNm": nm,
                    "reprtCode": f.get("reprt_code"), "bsnsYear": f.get("bsns_year"),
                    "marketCap": caps.get(f.get("stock_code") or ""),
                    "isCorrection": "정정" in nm or "정" in (f.get("rm") or ""),
                    "hasDocument": bool(f.get("hasDocument")), "url": dart_url(f["rcept_no"])})
        if len(out) >= limit:
            break
    return out


# ---- 종합 ----------------------------------------------------------------------------------------
def _market_of(c: dict, rows: list[dict]) -> str | None:
    if c.get("market"):
        return c["market"]
    latest = max(rows, key=lambda r: r.get("basDt", "")) if rows else {}
    m = (latest.get("mrktCtg") or "").upper()
    return {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KONEX": "KONEX"}.get(m)


def market_overview(source, market: str = "ALL") -> dict:
    market = (market or "ALL").upper()
    if market not in dict(MARKETS):
        raise ValueError(f"market은 {', '.join(m for m, _ in MARKETS)} 중 하나")
    sample = getattr(source, "name", "") == "sample"
    notes: list[str] = []
    history = source.market_history()
    corps = {c["stock_code"]: c for c in source.companies() if c.get("stock_code")}
    if not history:
        notes.append("시세 데이터가 없습니다. 실데이터는 DATA_GO_KR_API_KEY(공공데이터포털 주식시세정보)가 필요합니다.")

    # 종목별 최신 시가총액·시장 구분
    latest: dict[str, int] = {}
    mkt: dict[str, str | None] = {}
    names: dict[str, str] = {}
    for code, rows in history.items():
        if not rows:
            continue
        last = max(rows, key=lambda r: r.get("basDt", ""))
        names[code] = last.get("itmsNm") or code      # 기업 목록에 없는 종목(우선주 등)은 시세의 종목명을 쓴다
        if (cap := _cap(last)) is not None:
            latest[code] = cap
        mkt[code] = _market_of(corps.get(code, {}), rows)
    as_of = None
    all_days = sorted({r["basDt"] for rows in history.values() for r in rows if r.get("basDt")})
    if all_days:
        as_of = _iso(all_days[-1])

    counts = {m: 0 for m, _ in MARKETS}
    for code in latest:
        counts["ALL"] += 1
        if mkt.get(code) in counts:
            counts[mkt[code]] += 1
    selected = [c for c in latest if market == "ALL" or mkt.get(c) == market]

    # 시가총액 추이
    series = cap_series(history, selected)
    ranges = available_ranges(series)
    range_note = None
    if "5Y" not in ranges:
        span = len(series)
        range_note = ("샘플 시세는 1년치입니다." if sample else f"받아 둔 시세가 {span}개 거래일분입니다.") + \
                     " 더 긴 기간은 데이터가 쌓이면 열립니다."
    price_src = src("시세", "공공데이터포털 금융위원회_주식시세정보(getStockPriceInfo)" + (" · 가상 샘플" if sample else ""))
    capitalization = {"total": series[-1]["v"] if series else None, "series": series,
                      "changes": period_changes(series), "availableRanges": ranges, "rangeNote": range_note,
                      "source": price_src}

    # 지수 추이(시장 필터와 무관)
    indices = []
    for code, name in INDEX_NAMES:
        official = []
        try:
            official = source.index_series(name)
        except SourceError as e:
            notes.append(f"{name} 공식 지수를 받지 못해 대체 지수를 씁니다: {e}")
        if official:
            ser = sorted(({"d": _iso(r["basDt"]), "v": float(str(r["clpr"]).replace(",", ""))}
                          for r in official if r.get("basDt") and r.get("clpr")), key=lambda p: p["d"])
            kind, note = "official", f"{name} 일별 종가"
            isrc = src("시세", "공공데이터포털 금융위원회_지수시세정보(getStockMarketIndex)")
        else:
            members = [c for c in latest if mkt.get(c) == code]
            ser = proxy_index(cap_series(history, members))
            kind = "proxy"
            note = (f"공식 {name} 지수가 아닙니다. 추적 중인 {name} 상장 {len(members)}개사의 시가총액 합계를 "
                    f"첫날 = {PROXY_BASE:,.0f}으로 맞춘 대체 지수입니다(지수시세 키 DATA_GO_KR_API_KEY가 있으면 공식 지수로 바뀝니다).")
            isrc = src("계산", f"추적 기업 시가총액 합계 ÷ 기준일 합계 × {PROXY_BASE:,.0f}")
        indices.append({"code": code, "name": name if kind == "official" else f"{name}(대체)", "kind": kind,
                        "last": ser[-1]["v"] if ser else None, "asOf": ser[-1]["d"] if ser else None,
                        "series": ser, "changes": period_changes(ser), "availableRanges": available_ranges(ser),
                        "note": note, "source": isrc})

    # 업종 지도: 업종 코드가 목록에 없으면(실데이터) 시가총액 상위만 기업개황에서 불러온다
    items = []
    lookups = 0
    for code in sorted(selected, key=lambda c: -latest[c]):
        c = corps.get(code, {"corp_code": code, "corp_name": names.get(code, code), "stock_code": code})
        induty = c.get("induty_code")
        if not induty and hasattr(source, "induty_code") and lookups < INDUTY_LOOKUP_LIMIT and c.get("corp_code") != code:
            lookups += 1
            induty = source.induty_code(c["corp_code"])
        items.append({"corp_code": c.get("corp_code", code), "corp_name": c.get("corp_name", code),
                      "stock_code": code, "induty_code": induty, "cap": latest[code]})
    tree = sector_tree(items)
    if any(s["code"] is None for s in tree["children"]):
        notes.append(f"업종 코드를 확인하지 못한 기업은 '{UNKNOWN[1]}'으로 묶었습니다"
                     + ("" if sample else f"(실데이터는 시가총액 상위 {INDUTY_LOOKUP_LIMIT}개사만 기업개황에서 조회)") + ".")

    # 최근 정기보고서
    try:
        filings = source.recent_filings()
    except SourceError as e:
        filings, _ = [], notes.append(f"최근 정기보고서를 받지 못했습니다: {e}")
    corp_market = {c["corp_code"]: mkt.get(code) or c.get("market") for code, c in corps.items()}
    recent = recent_table(filings, latest, corp_market, market)

    # 새로 확인한 기업(적재 DB가 있을 때만). 첫 적재일에 들어온 회사는 신규가 아니다
    new = []
    if hasattr(source, "new_listings"):
        for c in source.new_listings(30):
            code = c.get("stock_code") or ""
            new.append({"corpCode": c["corp_code"], "corpName": c["corp_name"], "stockCode": code or None,
                        "market": c.get("market") or mkt.get(code), "firstSeen": str(c["first_seen"]),
                        "marketCap": latest.get(code)})
    new_note = ("일일 수집에서 처음 확인한 기업입니다. 확인일은 공식 상장일과 다를 수 있습니다."
                if hasattr(source, "new_listings") else "일일 수집(적재 DB)이 켜져 있을 때만 표시합니다.")

    universe = (f"추적 기업 {counts['ALL']}개사(가상 샘플)" if sample else f"상장 종목 {counts['ALL']:,}개")
    notes.append("시가총액은 종목별 시가총액(mrktTotAmt)의 합계입니다"
                 + ("" if sample else "(보통주·우선주 등 상장 종목을 각각 더함)") + ". 투자 판단 자료가 아닙니다.")
    return {"asOf": as_of, "market": market,
            "markets": [{"code": m, "label": lab, "count": counts[m]} for m, lab in MARKETS],
            "universeNote": universe, "sample": sample, "capitalization": capitalization, "indices": indices,
            "sectors": tree, "recentFilings": recent, "newListings": new, "newListingsNote": new_note,
            "ingested": bool(getattr(source, "ingested", False)), "notes": notes}


