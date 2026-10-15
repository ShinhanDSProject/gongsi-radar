"""검증: 1단(코드)과 2단(판정), 출력 필터와 재작성 후 재검증.

LLM이 쓴 문장이든 규칙이 쓴 문장이든 똑같이 이 모듈을 통과해야 한다.
  1단(코드): 인용 ID 존재, 금액·증감률 재계산 대조, 증감 방향, 근거 수준 재확인
  2단(판정): 인용 문단이 주장을 지지/불충분/모순 중 어디에 해당하는지
  출력 필터: 투자 권유·가치판단 표현 차단 → 재작성 → 필터와 1단을 다시 통과해야 함
"""
from __future__ import annotations

import re

from .classify import injection_suspected
from .relate import CAUSAL, DOWN, UP, assess, direction
from .textutil import parse_krw, parse_pct, sentences

# 유사투자자문업 금지 광고 목록과 금감원 적발 사례를 참고한 금지 표현(시작점, 팀에서 보강)
BANNED = [
    (r"강력\s*매수", "매매 권유"), (r"매수", "매매 권유"), (r"매도", "매매 권유"), (r"목표\s*주?가", "목표가"),
    (r"저평가", "가치판단"), (r"고평가", "가치판단"), (r"수익\s*보장", "수익 보장"), (r"추천\s*(?:종목|주)?", "추천"),
    (r"급등", "가격 전망"), (r"상승\s*(?:예상|전망|여력)", "가격 전망"), (r"투자\s*(?:유망|적기|매력)", "가치판단"),
    (r"사야\s*(?:한다|할)", "매매 권유"), (r"팔아야", "매매 권유"),
]
_BANNED_RE = [(re.compile(p), why) for p, why in BANNED]

# 규칙 재작성: 사실은 그대로 두고 표현만 바꾼다
_REWRITE = [
    (re.compile(r"매수를(?=\s*(?:결정|완료|진행|추진|실시))"), "취득을"),   # 자기주식 '매수를 결정' → '취득을 결정'
    (re.compile(r"(?<=자기주식)\s*매수(?=[\s,.)]|$)"), " 취득"),
    (re.compile(r"[‘'\"]?강력\s*매수[’'\"]?"), "[투자 판단 표현 삭제]"),
]


def check(name: str, ok: bool | None, detail: str = "") -> dict:
    status = "pass" if ok else ("warn" if ok is None else "fail")
    return {"name": name, "status": status, "detail": detail}


def banned_hits(text: str) -> list[str]:
    return [f"{m.group(0)}({why})" for rx, why in _BANNED_RE for m in rx.finditer(text or "")]


def rule_rewrite(text: str) -> str:
    out = text
    for rx, rep in _REWRITE:
        out = rx.sub(rep, out)
    if banned_hits(out):  # 그래도 남으면 해당 문장을 통째로 뺀다
        kept = [s for s in re.split(r"(?<=[.!?])\s+", out) if not banned_hits(s)]
        out = " ".join(kept) + " [투자 판단으로 읽힐 수 있는 표현을 삭제함]"
    return out.strip()


# ---- 관련 서술(수치 문장) 1단 -------------------------------------------------------
def _amount_ok(val_won: float, acct: dict) -> bool:
    for ref in (acct["current"], acct["prior"]):
        if abs(val_won - ref) <= max(0.5e8, abs(ref) * 0.005):
            return True
    return False


def verify_relation(rel: dict, acct: dict, block_ids: set[str], blocks: dict) -> list[dict]:
    st = rel["statement"]
    checks = []
    # 1. 인용 ID
    if rel["level"] == "확인 불가":
        checks.append(check("인용 ID 존재", True, "확인 불가 판정이라 인용 없음"))
    else:
        missing = [e["pid"] for e in rel["evidence"] if e["pid"] not in block_ids]
        checks.append(check("인용 ID 존재", not missing and bool(rel["evidence"]),
                            "모든 인용이 원문에 있음" if not missing else f"없는 ID: {', '.join(missing)}"))
    # 2. 금액
    amts = parse_krw(st)
    bad = [s for s, v in amts if not _amount_ok(v, acct)]
    checks.append(check("금액 대조(재무 API)", not bad,
                        f"{len(amts)}개 금액 일치" if not bad else f"재무 API와 다른 금액: {', '.join(bad)}"))
    # 3. 증감률
    pcts = parse_pct(st)
    y = acct["yoy_pct"]
    bad_p = [p for p in pcts if y is None or abs(p - abs(y)) > 0.06]
    checks.append(check("증감률 재계산", not bad_p,
                        f"계산값 {abs(y):.1f}%와 일치" if not bad_p else
                        f"문장 {', '.join(f'{p}%' for p in bad_p)} ≠ 계산값 {abs(y or 0):.1f}%"))
    # 4. 방향
    d = direction(y)
    head = sentences(st)[0] if st else ""  # '66.5%'의 소수점에서 자르지 않도록 문장 단위로
    wrong = (d == "감소" and UP.search(head) and not DOWN.search(head)) or (d == "증가" and DOWN.search(head) and not UP.search(head))
    checks.append(check("증감 방향", not wrong, f"재무 API 기준 {d}"))
    # 5. 근거 수준 재확인(코드)
    if rel["level"] == "인과 명시":
        b = blocks.get(rel["evidence"][0]["pid"]) if rel["evidence"] else None
        a = assess(acct["account_nm"], d, b) if b else {"level": "확인 불가"}
        checks.append(check("근거 수준 재확인", a["level"] == "인과 명시",
                            "인용 문장에 계정명·원인 표지·방향이 있음" if a["level"] == "인과 명시"
                            else f"코드 판정은 '{a['level']}' — 인과 명시로 볼 수 없음"))
        # 6. 공시 본문 수치 대조(경고만)
        if b:
            body_pcts = parse_pct(rel["evidence"][0].get("sentence") or b.text)
            if body_pcts and y is not None:
                match = any(abs(p - abs(y)) <= 0.06 for p in body_pcts)
                checks.append(check("본문 수치 대조", True if match else None,
                                    f"회사 서술의 {body_pcts[0]}%가 계산값과 일치" if match
                                    else f"회사 서술 {body_pcts}%와 계산값 {abs(y):.1f}%가 다름"))
    # 7. 출력 필터
    hits = banned_hits(st)
    checks.append(check("출력 필터", not hits, "금지 표현 없음" if not hits else ", ".join(hits)))
    return checks


def rule_judge(rel: dict, acct: dict) -> str:
    """2단 판정(규칙 버전): 인용이 주장을 지지/불충분/모순."""
    if rel["level"] == "확인 불가":
        return "해당 없음"
    sent = (rel["evidence"][0].get("sentence") or rel["evidence"][0]["text"]) if rel["evidence"] else ""
    d = direction(acct["yoy_pct"])
    if d == "감소" and UP.search(sent) and not DOWN.search(sent):
        return "모순"
    if d == "증가" and DOWN.search(sent) and not UP.search(sent):
        return "모순"
    if rel["level"] == "인과 명시":
        clause = rel.get("reason_clause") or ""
        return "지지" if clause and clause in sent and CAUSAL.search(sent) else "불충분"
    return "지지"  # 관련 맥락: '관련 서술은 있으나 원인 미기재'라는 주장 자체를 지지


# ---- 변경 문단 1단 --------------------------------------------------------------
def verify_change(item: dict, old_ids: set[str], new_ids: set[str], lawsuits: list[dict]) -> list[dict]:
    checks = []
    refs_ok = all(r["pid"] in old_ids for r in item["old"]) and all(r["pid"] in new_ids for r in item["new"])
    checks.append(check("인용 ID 존재", refs_ok, "원문 문단과 연결됨" if refs_ok else "원문에 없는 문단 ID"))
    from .align import _nums  # 순환 import 회피
    src = re.sub(r"\s+", " ", " ".join(r["text"] for r in item["old"] + item["new"]))
    sum_nums = [n for n in _nums(item["summary"]) if n not in src]  # 요약의 숫자는 원문에 그대로 있어야 함
    checks.append(check("요약 수치 대조", not sum_nums,
                        "요약의 숫자가 모두 원문에 있음" if not sum_nums else f"원문에 없는 숫자: {', '.join(sum_nums)}"))
    hits = banned_hits(item["summary"])
    checks.append(check("출력 필터", not hits, "금지 표현 없음" if not hits else ", ".join(hits)))
    if any(injection_suspected(r["text"]) for r in item["new"]):
        checks.append(check("문서 인젝션", None, "원문에 지시문으로 의심되는 문장 — 데이터로만 취급, 요약하지 않음"))
    if item["topic"] == "위험·소송" and item["edit_type"] == "신설" and lawsuits:
        txt = " ".join(r["text"] for r in item["new"])
        for ls in lawsuits:
            plaintiff = (ls.get("ac_ap") or "").strip()
            amt_hit = any(abs(v - w) < 1e8 for _, v in parse_krw(txt) for w in _won_in(ls.get("rq_cn", "")))
            if (plaintiff and plaintiff in txt) or amt_hit:
                checks.append(check("주요사항보고서 교차 확인", True,
                                    f"소송 등의 제기 공시({ls.get('lgd')}, 원고 {plaintiff})와 일치"))
                break
    return checks


def _won_in(text: str) -> list[float]:
    vals = [v for _, v in parse_krw(text)]
    vals += [float(x.replace(",", "")) for x in re.findall(r"([\d,]{5,})원", text)]
    return vals


def status_of(checks: list[dict], rewritten: bool = False) -> str:
    if any(c["status"] == "fail" for c in checks):
        return "반려"
    return "재작성 후 통과" if rewritten else "통과"
