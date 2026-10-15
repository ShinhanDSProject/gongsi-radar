"""수치 분석: 증감 계산(코드)과 '설명이 필요한 계정' 플래그(통계 규칙).

LLM은 여기서 아무것도 계산하지 않는다.
  - 증감률: 당기 보고서 한 건 안의 당기·전기 값을 비교(회사가 재작성한 전기 수치를 그대로 사용)
  - 업종 내 robust z: 피어 YoY 변화율의 중앙값·MAD 기준, |z| > 3
  - 중요성: 변동액이 매출액의 1% 이상이고 증감률이 30% 이상
"""
from __future__ import annotations

import statistics

from .config import FLAG_EXCLUDE, KEY_ACCOUNTS, MATERIALITY_REV_SHARE, MATERIALITY_YOY, ROBUST_Z

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
            cur, prior = amount(r.get("thstrm_add_amount")), amount(r.get("frmtrm_add_amount"))
            basis = "누적"
        else:
            cur, prior = amount(r.get("thstrm_amount")), amount(r.get("frmtrm_amount"))
            basis = "전기말" if (reprt_code in _PERIODIC_ADD and sj == "BS") else "연간"
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


def robust_z(x: float, sample: list[float]) -> float | None:
    if len(sample) < 8:
        return None
    med = statistics.median(sample)
    mad = statistics.median([abs(v - med) for v in sample])
    if mad == 0:
        return None
    return 0.6745 * (x - med) / mad


def add_flags(changes: list[dict], peer_rows: list[dict] | None) -> None:
    rev = next((c["current"] for c in changes if c["account_nm"] in ("매출액", "수익(매출액)", "영업수익")), None)
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
