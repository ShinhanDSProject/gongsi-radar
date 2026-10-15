"""수치 분석: 증감 계산(코드)과 '설명이 필요한 계정' 플래그(통계 규칙).

LLM은 여기서 아무것도 계산하지 않는다.
  - 증감률: 당기 보고서 한 건 안의 당기·전기 값을 비교(회사가 재작성한 전기 수치를 그대로 사용)
  - 업종 내 robust z: 피어 YoY 변화율의 중앙값·MAD 기준, |z| > 3
  - 중요성: 변동액이 매출액의 1% 이상이고 증감률이 30% 이상
explain_accounts가 위 계산을 계산식·출처(Formula)로 다시 펼쳐 accounts[].formulas에 붙인다.
"""
from __future__ import annotations

import statistics

from radar.config import FLAG_EXCLUDE, KEY_ACCOUNTS, MATERIALITY_REV_SHARE, MATERIALITY_YOY, ROBUST_Z
from radar.numbers.formula import fin_source, formula, inp, src

_PERIODIC_ADD = {"11012", "11013", "11014"}  # 분·반기: 손익은 누적 금액으로 비교


def amount(s) -> int | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = int(float(s))
    except ValueError:
        return None
    return -v if neg else v


def _nm(s: str) -> str:
    return "".join((s or "").split())


def account_key(row: dict) -> str:
    aid = row.get("account_id") or ""
    if aid and "미사용" not in aid:
        return f"{row.get('sj_div')}:{aid}"
    return f"{row.get('sj_div')}:nm:{_nm(row.get('account_nm'))}"


def account_changes(rows: list[dict], reprt_code: str) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        key = account_key(r)
        if key in seen:
            continue
        seen.add(key)
        sj = r.get("sj_div")
        if reprt_code in _PERIODIC_ADD and sj in ("IS", "CIS") and r.get("thstrm_add_amount"):
            fc, fp = "thstrm_add_amount", "frmtrm_add_amount"
            basis = "누적"
        else:
            fc, fp = "thstrm_amount", "frmtrm_amount"
            basis = "전기말" if (reprt_code in _PERIODIC_ADD and sj == "BS") else "연간"
        cur, prior = amount(r.get(fc)), amount(r.get(fp))
        if cur is None or prior is None:
            continue
        delta = cur - prior
        yoy = (delta / abs(prior)) if prior else None
        nm = r.get("account_nm", "")
        out.append({
            "key": key, "account_id": r.get("account_id"), "account_nm": nm, "sj_div": sj, "basis": basis,
            "current": cur, "prior": prior, "delta": delta,
            "yoy_pct": round(yoy * 100, 2) if yoy is not None else None,
            "is_key": r.get("account_id") in KEY_ACCOUNTS or nm in KEY_ACCOUNTS.values(),
            "flags": [], "robust_z": None, "peer_n": 0,
            # 내부용: 계산식 출처. explain_accounts가 꺼내 쓰고 지운다(리포트에 남지 않음)
            "_src": {"rcept_no": r.get("rcept_no"), "bsns_year": r.get("bsns_year"), "account_nm": nm,
                     "cur": fc, "prior": fp},
        })
    return out


def _peer_yoy(peer_rows: list[dict]) -> dict[str, list[float]]:
    by_acct: dict[str, list[float]] = {}
    for r in peer_rows:
        cur, prior = amount(r.get("thstrm_amount")), amount(r.get("frmtrm_amount"))
        if cur is None or not prior:
            continue
        by_acct.setdefault(_nm(r.get("account_nm")), []).append((cur - prior) / abs(prior))
    return by_acct


def peer_stats(sample: list[float]) -> tuple[float | None, float | None]:
    """피어 YoY 변화율의 (중앙값, MAD)."""
    if not sample:
        return None, None
    med = statistics.median(sample)
    return med, statistics.median([abs(v - med) for v in sample])


def robust_z(x: float, sample: list[float]) -> float | None:
    if len(sample) < 8:
        return None
    med, mad = peer_stats(sample)
    if mad == 0:
        return None
    return 0.6745 * (x - med) / mad


def _revenue(changes: list[dict]) -> int | None:
    return next((c["current"] for c in changes if c["account_nm"] in ("매출액", "수익(매출액)", "영업수익")), None)


def add_flags(changes: list[dict], peer_rows: list[dict] | None) -> None:
    rev = _revenue(changes)
    peers = _peer_yoy(peer_rows or [])
    for c in changes:
        y = c["yoy_pct"]
        if y is None:
            continue
        sample = peers.get(_nm(c["account_nm"]))
        if sample:
            z = robust_z(y / 100, sample)
            c["peer_n"] = len(sample)
            if z is not None:
                c["robust_z"] = round(z, 2)
                if abs(z) > ROBUST_Z:
                    c["flags"].append(f"업종 대비 이례적(robust z {z:+.1f}, 피어 {len(sample)}개사)")
        if (rev and c["account_nm"] not in FLAG_EXCLUDE and not c["is_key"]
                and abs(c["delta"]) >= MATERIALITY_REV_SHARE * abs(rev) and abs(y) >= MATERIALITY_YOY * 100):
            c["flags"].append(f"중요성 기준(변동액 매출 대비 {abs(c['delta']) / abs(rev):.1%}, 증감률 {y:+.1f}%)")


def targets(changes: list[dict]) -> list[dict]:
    """관련 서술을 연결할 계정: 핵심 손익 계정 + 플래그가 뜬 계정."""
    key = [c for c in changes if c["is_key"]]
    flagged = [c for c in changes if c["flags"] and not c["is_key"]]
    order = {"매출액": 0, "영업이익": 1, "당기순이익": 2}
    key.sort(key=lambda c: order.get(c["account_nm"], 9))
    flagged.sort(key=lambda c: -abs(c["delta"]))
    return key + flagged


def _materiality_target(c: dict) -> bool:
    return c["account_nm"] not in FLAG_EXCLUDE and not c["is_key"]


def explain_accounts(changes: list[dict], fs_div: str, peer_rows: list[dict] | None) -> None:
    """accounts[].formulas: delta·yoy·robust_z(피어 있을 때)·materiality(중요성 기준 대상일 때).

    add_flags 다음에 부른다. 내부 키 _src는 여기서 지운다.
    """
    rev = _revenue(changes)
    rev_c = next((c for c in changes if c["account_nm"] in ("매출액", "수익(매출액)", "영업수익")), None)
    peers = _peer_yoy(peer_rows or [])
    for c in changes:
        s = c.pop("_src", None) or {}
        row = {"rcept_no": s.get("rcept_no"), "bsns_year": s.get("bsns_year"), "account_nm": c["account_nm"]}
        s_cur = fin_source(row, s.get("cur", "thstrm_amount"), fs_div=fs_div)
        s_prior = fin_source(row, s.get("prior", "frmtrm_amount"), fs_div=fs_div)
        cur_in = inp("당기", c["current"], "원", s_cur, note=c["basis"])
        prior_in = inp("전기", c["prior"], "원", s_prior)
        fs = [formula("delta", f"{c['account_nm']} 변동액", "당기 − 전기", [cur_in, prior_in], c["delta"], "원")]
        fs.append(formula(
            "yoy", f"{c['account_nm']} 증감률", "(당기 − 전기) ÷ |전기| × 100",
            [inp("변동액", c["delta"], "원", src("계산", "당기 − 전기")), prior_in], c["yoy_pct"], "%",
            reason=None if c["yoy_pct"] is not None else "전기 값이 0이라 증감률을 계산하지 않음",
            notes=["당기 보고서 한 건 안의 당기·전기 값을 비교(회사가 재작성한 전기 수치 그대로)"]))
        sample = peers.get(_nm(c["account_nm"]))
        if sample:
            med, mad = peer_stats(sample)
            x = c["yoy_pct"] / 100 if c["yoy_pct"] is not None else None
            peer_src = src("업종 피어", f"피어 {len(sample)}개사 {c['account_nm']} YoY 변화율")
            if x is None:
                why = "증감률이 없어 계산하지 않음"
            elif len(sample) < 8:
                why = f"피어 {len(sample)}개사로 8개사 미만"
            elif mad == 0:
                why = "피어 MAD가 0"
            else:
                why = None
            fs.append(formula(
                "robust_z", f"{c['account_nm']} 업종 내 robust z", "0.6745 × (x − 피어 중앙값) ÷ MAD",
                [inp("x(이 회사 YoY 변화율)", round(x, 6) if x is not None else None, "비율", src("계산", "증감률 ÷ 100")),
                 inp("피어 중앙값", round(med, 6), "비율", peer_src),
                 inp("MAD", round(mad, 6), "비율", peer_src, note="피어 변화율과 중앙값 차이의 절댓값 중앙값"),
                 inp("n", len(sample), "개사", peer_src)],
                c["robust_z"], "", reason=why,
                notes=[f"|z| > {ROBUST_Z:g}이면 '업종 대비 이례적' 플래그"]))
        if rev and _materiality_target(c):
            share = abs(c["delta"]) / abs(rev) * 100
            hit = abs(c["delta"]) >= MATERIALITY_REV_SHARE * abs(rev) and c["yoy_pct"] is not None \
                and abs(c["yoy_pct"]) >= MATERIALITY_YOY * 100
            rev_src = fin_source({**row, "account_nm": rev_c["account_nm"]}, "thstrm_amount", fs_div=fs_div) if rev_c else None
            fs.append(formula(
                "materiality", f"{c['account_nm']} 중요성 기준", "|변동액| ÷ |매출액| × 100",
                [inp("변동액", c["delta"], "원", src("계산", "당기 − 전기")), inp("매출액", rev, "원", rev_src),
                 inp("증감률", c["yoy_pct"], "%", src("계산", "증감률"))],
                share, "%", digits=2,
                notes=[f"기준: 매출 대비 {MATERIALITY_REV_SHARE:.0%} 이상 그리고 |증감률| {MATERIALITY_YOY:.0%} 이상",
                       "기준 충족" if hit else "기준 미충족"]))
        c["formulas"] = fs
