"""지배구조: 최대주주·임원·타법인 출자와 변동, 관계 그래프 (docs/CONTRACT.md §6.4).

입력은 OpenDART 정기보고서 주요정보 응답 행 그대로(hyslrSttus·exctvSttus·otrCprInvstmntSttus).
  주주·출자 변동: 당기 보고서 한 건 안의 기초·기말 비교(회사가 공시한 값)
  임원 변동:     전기 보고서 임원 목록과 비교(이름+출생년월로 같은 사람 판단)
  그래프:        회사 ← 주주(지분율) · 회사 ← 임원(직위) · 회사 → 출자회사(지분율). 이름이 회사 목록과 같으면 corpCode 연결
표의 '-'는 보유 없음(0)으로 읽는다. 판단 문구는 만들지 않는다.
"""
from __future__ import annotations

import re

from radar.numbers.financials import amount

_TOTAL = {"계", "합계", "총계", "소계"}
_CORP_MARK = re.compile(r"㈜|\(주\)|주식회사|\s+")
NOTE = ("OpenDART 정기보고서 주요정보(최대주주 현황·임원 현황·타법인 출자 현황) 기준입니다. 주주·출자 변동은 당기 보고서의 "
        "기초·기말 값을, 임원 변동은 전기 보고서 목록과 비교했습니다. 출자 장부가액은 공시 단위 그대로입니다.")


def norm_name(s: str) -> str:
    """회사명 비교용: ㈜·(주)·주식회사·공백 제거."""
    return _CORP_MARK.sub("", s or "")


def known_names(companies: list[dict]) -> dict[str, str]:
    """회사 목록 → {정규화 이름: corp_code}."""
    return {norm_name(c["corp_name"]): c["corp_code"] for c in companies}


def _pct(s) -> float | None:
    if s is None:
        return None
    t = str(s).replace(",", "").replace("%", "").strip()
    if t in ("", "-"):
        return 0.0  # 표의 '-'는 보유 없음
    try:
        return float(t)
    except ValueError:
        return None


def _shares(s) -> int | None:
    t = str(s or "").strip()
    return 0 if t in ("", "-") else amount(t)


def _total_row(nm: str) -> bool:
    return norm_name(nm) in _TOTAL


def _holding_change(b: float | None, e: float | None, kind: str) -> str:
    b0, e0 = b or 0.0, e or 0.0
    if b0 == 0 and e0 > 0:
        return "신규"
    if b0 > 0 and e0 == 0:
        return "전량 처분" if kind == "주주" else "처분"
    if e0 > b0:
        return "증가" if kind == "주주" else "지분 증가"
    if e0 < b0:
        return "감소" if kind == "주주" else "지분 감소"
    return "변동 없음"


def shareholders(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        nm = (r.get("nm") or "").strip()
        if not nm or _total_row(nm):
            continue
        b, e = _pct(r.get("bsis_posesn_stock_qota_rt")), _pct(r.get("trmend_posesn_stock_qota_rt"))
        out.append({"name": nm, "relation": r.get("relate") or "", "stockKind": r.get("stock_knd") or "",
                    "beginShares": _shares(r.get("bsis_posesn_stock_co")), "beginPct": b,
                    "endShares": _shares(r.get("trmend_posesn_stock_co")), "endPct": e,
                    "change": _holding_change(b, e, "주주"),
                    "deltaPct": round(e - b, 2) if b is not None and e is not None else None})
    return out


def _exec_key(r: dict) -> tuple[str, str]:
    return (r.get("nm") or "").strip(), (r.get("birth_ym") or "").strip()


def _exec_row(r: dict, change: str, prior_pos: str | None) -> dict:
    return {"name": (r.get("nm") or "").strip(), "position": r.get("ofcps") or "",
            "registered": (r.get("rgist_exctv_at") or "") == "등기임원", "fullTime": (r.get("fte_at") or "") == "상근",
            "duty": r.get("chrg_job") or "", "change": change, "priorPosition": prior_pos}


def executives(cur: list[dict], prior: list[dict] | None) -> list[dict]:
    pmap = {_exec_key(r): r for r in (prior or []) if r.get("nm")}
    out = []
    for r in cur:
        if not r.get("nm"):
            continue
        p = pmap.get(_exec_key(r))
        if prior is None:
            out.append(_exec_row(r, "유지", None))  # 전기 보고서가 없으면 비교하지 않음(note에 남김)
        elif p is None:
            out.append(_exec_row(r, "신규 선임", None))
        elif (p.get("ofcps") or "") != (r.get("ofcps") or ""):
            out.append(_exec_row(r, "직위 변경", p.get("ofcps")))
        else:
            out.append(_exec_row(r, "유지", p.get("ofcps")))
    cur_keys = {_exec_key(r) for r in cur}
    for k, p in pmap.items():
        if k not in cur_keys:
            out.append(_exec_row(p, "퇴임", p.get("ofcps")))
    return out


def investments(rows: list[dict], known: dict[str, str]) -> list[dict]:
    out = []
    for r in rows:
        nm = (r.get("inv_prm") or "").strip()
        if not nm or _total_row(nm):
            continue
        b, e = _pct(r.get("bsis_blce_qota_rt")), _pct(r.get("trmend_blce_qota_rt"))
        out.append({"name": nm, "purpose": r.get("invstmnt_purps") or "", "beginPct": b, "endPct": e,
                    "bookValue": _shares(r.get("trmend_blce_acntbk_amount")),
                    "change": _holding_change(b, e, "출자"), "corpCode": known.get(norm_name(nm))})
    return out


def _fmt(p: float | None) -> str:
    return "-" if p is None else f"{p:.2f}%"


def change_texts(sh: list[dict], ex: list[dict], inv: list[dict]) -> list[dict]:
    out = []
    for s in sh:
        if s["change"] != "변동 없음":
            rel = f" [{s['relation']}]" if s["relation"] else ""
            out.append({"kind": "주주", "text": f"{s['name']}{rel} 지분 {_fmt(s['beginPct'])} → "
                                                f"{_fmt(s['endPct'])} ({s['change']})"})
    for e in ex:
        if e["change"] == "신규 선임":
            out.append({"kind": "임원", "text": f"{e['name']} {e['position']} 신규 선임"})
        elif e["change"] == "퇴임":
            out.append({"kind": "임원", "text": f"{e['name']} {e['priorPosition'] or e['position']} 퇴임"})
        elif e["change"] == "직위 변경":
            out.append({"kind": "임원", "text": f"{e['name']} 직위 변경: {e['priorPosition']} → {e['position']}"})
    for i in inv:
        if i["change"] == "신규":
            out.append({"kind": "출자", "text": f"{i['name']} 신규 출자(기말 지분 {_fmt(i['endPct'])}, {i['purpose']})"})
        elif i["change"] != "변동 없음":
            out.append({"kind": "출자", "text": f"{i['name']} 지분 {_fmt(i['beginPct'])} → {_fmt(i['endPct'])} ({i['change']})"})
    return out


def build_graph(company: dict | None, sh: list[dict], ex: list[dict], inv: list[dict], known: dict[str, str]) -> dict:
    nodes: dict[str, dict] = {}
    edges = []
    cid = "company"
    nodes[cid] = {"id": cid, "label": (company or {}).get("corp_name") or "회사", "kind": "company",
                  "corpCode": (company or {}).get("corp_code")}

    def pnode(name: str, kind: str) -> str:
        nid = "p:" + norm_name(name)
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": name, "kind": kind, "corpCode": known.get(norm_name(name))}
        return nid

    for s in sh:
        nid = pnode(s["name"], "shareholder")
        label = f"지분 {_fmt(s['endPct'])}" if s["change"] != "전량 처분" else f"전량 처분(기초 {_fmt(s['beginPct'])})"
        edges.append({"from": nid, "to": cid, "pct": s["endPct"], "label": label})
    for e in ex:
        if e["change"] == "퇴임":
            continue
        nid = pnode(e["name"], "person")
        edges.append({"from": nid, "to": cid, "pct": None, "label": e["position"]})
    for i in inv:
        nid = "i:" + norm_name(i["name"])
        nodes.setdefault(nid, {"id": nid, "label": i["name"], "kind": "investee", "corpCode": i["corpCode"]})
        label = f"출자 {_fmt(i['endPct'])}" if i["change"] != "처분" else "처분"
        edges.append({"from": cid, "to": nid, "pct": i["endPct"], "label": label})
    return {"nodes": list(nodes.values()), "edges": edges}


def build_governance(cur: dict, prior: dict | None, known: dict[str, str] | None = None,
                     company: dict | None = None) -> dict:
    """Governance(§6.4). cur·prior: source.governance(...) 결과. known: {정규화 이름: corp_code}(known_names)."""
    known = known or {}
    sh = shareholders(cur.get("shareholders") or [])
    ex = executives(cur.get("executives") or [], (prior or {}).get("executives") if prior else None)
    inv = investments(cur.get("investments") or [], known)
    note = NOTE if prior else NOTE + " 전기 보고서 지배구조 데이터가 없어 임원 변동은 비교하지 않았습니다."
    return {"rceptNo": cur.get("rcept_no") or "", "priorRceptNo": (prior or {}).get("rcept_no") if prior else None,
            "shareholders": sh, "executives": ex, "investments": inv, "changes": change_texts(sh, ex, inv),
            "graph": build_graph(company, sh, ex, inv, known), "note": note}
