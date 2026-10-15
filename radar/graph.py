"""고정 DAG 파이프라인.

  수집·파싱 → 수치 분석 → 본문 비교 → 관련 서술 연결 → 검증 ─(통과)→ Report Writer
                                         ↑                 │
                                         └──(반려, 최대 2회)─┘

분석 1건의 순서는 항상 같으므로 Manager가 워커를 고르지 않는다. 동적으로 갈라지는 곳은 검증 반려 루프 하나다.
LangGraph가 설치되어 있으면 StateGraph로, 없으면 같은 토폴로지의 내장 러너로 실행한다(RADAR_GRAPH=builtin으로 강제).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TypedDict

from . import financials as finmod
from .align import diff_documents, number_changes, word_diff
from .classify import INJECTION_SUMMARY, importance, injection_suspected, topic_of
from .config import ALIGN_THRESHOLDS, MAX_VERIFY_RETRIES, PIPELINE_VERSION, RELATE_SECTIONS, Settings
from .embed import kind_of
from .llm import PRICE_PER_M, RuleLLM
from .parser import ParsedDoc, parse_filing_zip
from .relate import direction, numeric_claims, rule_relate, top_candidates_for_llm
from .sources import REPRT
from .tables import diff_tables
from .textutil import norm_ws
from .verify import banned_hits, check, status_of, verify_change, verify_relation

LABELS = {"ingest": "수집·파싱", "numbers": "수치 분석", "diff": "본문 비교",
          "relate": "관련 서술 연결", "verify": "검증", "report": "Report Writer"}
DISCLAIMER = ("이 리포트는 생성형 AI가 공시 원문을 비교해 만든 초안이며, 사람 검토를 거쳐 공유됩니다. "
              "투자 판단이나 매매 권유가 아니며, 원문과 다를 수 있으니 반드시 DART 원문을 확인하세요. 출처: DART")


@dataclass
class Ctx:
    settings: Settings
    source: Any
    embedder: Any
    llm: Any
    on_event: Callable[[dict], None] = lambda e: None
    t0: float = field(default_factory=time.time)
    analysis_id: str = ""
    request_uid: str | None = None


class RadarState(TypedDict, total=False):
    ctx: Any
    request: dict
    company: dict
    filings: dict
    docs: dict
    fin_rows: list
    fs_div: str
    peers: list
    lawsuits: list
    accounts: list
    targets: list
    changes: list
    tables: list
    relations: dict
    pending: list
    feedback: dict
    round: int
    timeline: list
    report: dict


def _ms(ctx: Ctx) -> int:
    return int((time.time() - ctx.t0) * 1000)


def node(name: str):
    """타임라인 기록 + 진행 이벤트 발행."""
    def deco(fn):
        def run(state: RadarState) -> dict:
            ctx: Ctx = state["ctx"]
            start = _ms(ctx)
            ctx.on_event({"type": "node_start", "node": name, "label": LABELS[name], "round": state.get("round", 0)})
            update = fn(state)
            note = update.pop("_note", "")
            status = update.pop("_status", "ok")
            entry = {"node": name, "label": LABELS[name], "round": state.get("round", 0),
                     "started_ms": start, "ended_ms": _ms(ctx), "status": status, "note": note}
            ctx.on_event({"type": "node_end", **entry})
            update["timeline"] = list(state.get("timeline", [])) + [entry]
            return update
        run.__name__ = fn.__name__
        return run
    return deco


# ---- 노드 ---------------------------------------------------------------------
@node("ingest")
def ingest(state: RadarState) -> dict:
    ctx: Ctx = state["ctx"]
    src, req = ctx.source, state["request"]
    company = src.resolve(str(req["company"]))
    year, code = int(req["bsns_year"]), str(req["reprt_code"])
    cur = src.find_report(company["corp_code"], year, code)
    prior = src.find_report(company["corp_code"], year - 1, code)
    docs = {"current": parse_filing_zip(src.document(cur["rcept_no"]), cur["rcept_no"]),
            "prior": parse_filing_zip(src.document(prior["rcept_no"]), prior["rcept_no"])}
    fin_rows, fs_div = src.financials(company["corp_code"], year, code)
    peers = src.peers(company["corp_code"], year, code)
    lawsuits = src.lawsuits(company["corp_code"], f"{year}0101", cur["rcept_dt"])
    d = docs["current"]
    return {"company": company, "filings": {"current": cur, "prior": prior}, "docs": docs, "fin_rows": fin_rows,
            "fs_div": fs_div, "peers": peers, "lawsuits": lawsuits,
            "_note": f"원문 2건 파싱(본문 {d.chosen_file}, {d.encoding_used}), 재무 {fs_div}, 피어 {len({p.get('corp_code') for p in peers})}개사"}


@node("numbers")
def numbers(state: RadarState) -> dict:
    accts = finmod.account_changes(state["fin_rows"], state["request"]["reprt_code"])
    finmod.add_flags(accts, state["peers"])
    targets = finmod.targets(accts)
    flagged = sum(1 for a in accts if a["flags"])
    return {"accounts": accts, "targets": [t["key"] for t in targets],
            "_note": f"계정 {len(accts)}개 증감 계산, 플래그 {flagged}개, 관련 서술 연결 대상 {len(targets)}개"}


def _ref(b) -> dict:
    return {"pid": b.id, "section_path": b.section_path, "text": b.text, "sentence": None}


@node("diff")
def diff(state: RadarState) -> dict:
    ctx: Ctx = state["ctx"]
    old, new = state["docs"]["prior"], state["docs"]["current"]
    th = ALIGN_THRESHOLDS[kind_of(ctx.embedder)]
    raw = diff_documents(old, new, ctx.embedder, th)
    rule = RuleLLM()
    items, seen = [], {}
    for rc in raw:
        if rc.edit_type == "동일":
            continue
        in_target = rc.section_key.startswith(RELATE_SECTIONS)
        item = {"id": "", "section_key": rc.section_key, "section_path": rc.section_path, "edit_type": rc.edit_type,
                "old": [_ref(b) for b in rc.old], "new": [_ref(b) for b in rc.new], "similarity": rc.similarity,
                "diff": word_diff(rc.old_text, rc.new_text) if rc.old and rc.new else [],
                "numbers": number_changes(rc.old_text, rc.new_text) if rc.old and rc.new else [],
                "flags": list(rc.flags), "duplicates": [], "in_target_section": in_target,
                "summary_before_rewrite": None}
        sig = (rc.edit_type, norm_ws(rc.old_text), norm_ws(rc.new_text))
        if sig in seen:  # 같은 변경이 다른 섹션(II-5와 주석 등)에 반복되면 한 번만 보고
            seen[sig]["duplicates"].append(rc.section_path)
            continue
        seen[sig] = item
        inj = injection_suspected(rc.new_text)
        if inj:
            item["topic"] = topic_of(rc.new_text, rc.section_key)
            item["summary"] = INJECTION_SUMMARY
            item["flags"].append("지시문 의심")
        else:
            s = (ctx.llm if in_target else rule).summarize_change(item)
            item["topic"], item["summary"] = s["topic"], s["summary"]
        item["importance"] = importance(item["topic"], item["edit_type"], in_target, inj, rc.new_text or rc.old_text)
        items.append(item)
    items.sort(key=lambda x: -x["importance"])
    for k, it in enumerate(items, 1):
        it["id"] = f"C{k:02d}"
    tables = diff_tables(old, new)
    by = {}
    for it in items:
        by[it["edit_type"]] = by.get(it["edit_type"], 0) + 1
    dup = sum(len(i["duplicates"]) for i in items)
    inj = sum("지시문 의심" in i["flags"] for i in items)
    return {"changes": items, "tables": tables,
            "_note": " · ".join(f"{k} {v}" for k, v in by.items()) + f" | 표 {len(tables)}개 | 중복 제거 {dup}건 | 지시문 의심 {inj}건"}


@node("relate")
def relate(state: RadarState) -> dict:
    ctx: Ctx = state["ctx"]
    doc: ParsedDoc = state["docs"]["current"]
    accts = {a["key"]: a for a in state["accounts"]}
    relations = dict(state.get("relations") or {})
    pending = state.get("pending") or state["targets"]
    feedback = state.get("feedback") or {}
    rnd = state.get("round", 0)
    exclude = {r["pid"] for c in state["changes"] if "지시문 의심" in c["flags"] for r in c["new"]}
    for key in pending:
        a = accts[key]
        res = rule_relate(a, doc, ctx.embedder, exclude)
        if type(ctx.llm) is not RuleLLM:  # LLM 모드: 후보 문단을 Spotlighting해서 넘기고, 판정은 아래 검증이 다시 한다
            cands = top_candidates_for_llm(a, doc, ctx.embedder, exclude)
            res = ctx.llm.relate(a, res, cands, feedback.get(key))
        res = dict(res)
        fault = False
        if ctx.settings.demo_fault_injection and rnd == 0 and a["account_nm"] == "영업이익" and a["yoy_pct"]:
            right = f"{abs(a['yoy_pct']):.1f}%"
            res["statement"] = res["statement"].replace(right, f"{abs(a['yoy_pct']) - 4:.1f}%", 1)
            fault = True
        prev = relations.get(key, {})
        relations[key] = {
            "account_key": key, "account_nm": a["account_nm"], "direction": direction(a["yoy_pct"]),
            "yoy_pct": a["yoy_pct"], "current": a["current"], "prior": a["prior"],
            "level": res["level"], "statement": res["statement"], "statement_before_rewrite": None,
            "reason_clause": res.get("clause"), "why": res.get("why", ""), "evidence": res["evidence"],
            "numeric_claims": numeric_claims(a), "attempts": prev.get("attempts", []), "_fault": fault,
        }
    lv = {}
    for k in pending:
        lv[relations[k]["level"]] = lv.get(relations[k]["level"], 0) + 1
    return {"relations": relations,
            "_note": (f"{rnd + 1}차: " if rnd else "") + f"{len(pending)}개 계정 · "
                     + " · ".join(f"{k} {v}" for k, v in lv.items())}


@node("verify")
def verify(state: RadarState) -> dict:
    ctx: Ctx = state["ctx"]
    doc: ParsedDoc = state["docs"]["current"]
    blocks = doc.by_id()
    ids = set(blocks)
    accts = {a["key"]: a for a in state["accounts"]}
    relations = {k: dict(v) for k, v in state["relations"].items()}
    pending = state.get("pending") or state["targets"]
    rnd = state.get("round", 0)
    rejected, feedback = [], {}

    for key in pending:
        rel, a = relations[key], accts[key]
        checks = verify_relation(rel, a, ids, blocks)
        rewritten = False
        hits = banned_hits(rel["statement"])
        if hits:  # 출력 필터 → 재작성 → 같은 필터와 1단 검증을 다시 통과해야 함
            rel["statement_before_rewrite"] = rel["statement"]
            rel["statement"] = ctx.llm.rewrite(rel["statement"], hits)
            checks = verify_relation(rel, a, ids, blocks)
            rewritten = True
        judge = ctx.llm.judge(rel, a)
        if judge == "모순":
            checks.append(check("2단 판정", False, "인용 문단이 주장과 모순"))
        else:
            checks.append(check("2단 판정", judge != "불충분" or rel["level"] != "인과 명시", f"판정: {judge}"))
        status = status_of(checks, rewritten)
        reason = "; ".join(f"{c['name']}: {c['detail']}" for c in checks if c["status"] == "fail")
        rel["attempts"] = rel["attempts"] + [{"attempt": rnd + 1, "status": status, "reason": reason or "모든 검사 통과",
                                              "statement": rel["statement"], "fault_injected": rel.pop("_fault", False)}]
        rel["verification"] = {"status": status, "checks": checks, "judge": judge}
        if status == "반려":
            rejected.append(key)
            feedback[key] = reason
        relations[key] = rel

    changes = state["changes"]
    if rnd == 0:  # 변경 문단은 한 번만 검증(재생성 대신 재작성)
        old_ids = set(state["docs"]["prior"].by_id())
        changes = []
        for it in state["changes"]:
            it = dict(it)
            checks = verify_change(it, old_ids, ids, state["lawsuits"])
            rewritten = False
            hits = banned_hits(it["summary"])
            if hits:
                it["summary_before_rewrite"] = it["summary"]
                it["summary"] = ctx.llm.rewrite(it["summary"], hits)
                checks = verify_change(it, old_ids, ids, state["lawsuits"])
                rewritten = True
                it["flags"] = it["flags"] + ["표현 완화"]
            st = status_of(checks, rewritten)
            if st == "반려" or "지시문 의심" in it["flags"]:  # 인젝션 의심은 사람이 원문을 직접 확인해야 함
                st = "검토 필요"
            it["verification"] = {"status": st, "checks": checks, "judge": None}
            changes.append(it)

    next_round = rnd + 1
    if rejected and next_round <= MAX_VERIFY_RETRIES:
        nxt, status = rejected, "rejected"
        note = f"반려 {len(rejected)}건 → 관련 서술 연결 재실행: " + "; ".join(
            f"{relations[k]['account_nm']}({feedback[k][:60]})" for k in rejected)
    else:
        for k in rejected:  # 재실행 상한 도달: 사람 검토로 넘김
            relations[k]["verification"]["status"] = "검토 필요"
        nxt, status = [], "ok"
        passed = sum(1 for k in pending if relations[k]["verification"]["status"] != "검토 필요")
        note = f"{passed}/{len(pending)}건 통과" + (f", 검토 필요 {len(rejected)}건" if rejected else "")
    return {"relations": relations, "changes": changes, "pending": nxt, "feedback": feedback,
            "round": next_round, "_status": status, "_note": note}


def route_after_verify(state: RadarState) -> str:
    return "relate" if state.get("pending") else "report"


@node("report")
def report(state: RadarState) -> dict:
    ctx: Ctx = state["ctx"]
    req, s = state["request"], ctx.settings
    docs = state["docs"]
    cur, prior = state["filings"]["current"], state["filings"]["prior"]

    def filing(f):
        return {"rcept_no": f["rcept_no"], "report_nm": f["report_nm"], "rcept_dt": f["rcept_dt"],
                "bsns_year": int(f["bsns_year"]), "reprt_code": f["reprt_code"], "url": f["url"]}

    relations = [state["relations"][k] for k in state["targets"]]
    for r in relations:
        r.pop("_fault", None)
    llm_usage = getattr(ctx.llm, "usage", {})
    changed_chars = sum(len(r["text"]) for c in state["changes"] for r in c["old"] + c["new"] if c["in_target_section"])
    est_in = int(changed_chars / 1.5) + 800 * len(state["changes"])
    est_cost = est_in / 1e6 * PRICE_PER_M["small_in"] + (20_000 / 1e6 * PRICE_PER_M["large_in"] + 3_000 / 1e6 * PRICE_PER_M["large_out"])
    rep = {
        "meta": {
            "analysis_id": ctx.analysis_id, "request_uid": ctx.request_uid,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "company": state["company"], "current": filing(cur), "prior": filing(prior),
            "source": ctx.source.name, "fs_div": state["fs_div"], "embedder": ctx.embedder.name, "llm": ctx.llm.name,
            "pipeline_version": PIPELINE_VERSION, "graph_engine": state.get("_engine", "builtin"),
            "demo_fault_injection": s.demo_fault_injection, "sample_data": ctx.source.name == "sample",
            "disclaimer": DISCLAIMER,
        },
        "parse": {"current": docs["current"].stats(), "prior": docs["prior"].stats()},
        "accounts": state["accounts"],
        "changes": state["changes"],
        "tables": state["tables"],
        "relations": relations,
        "timeline": [],
        "review": {"status": "검토 대기", "reviewer": None, "decided_at": None, "comment": None,
                   "events": [{"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "actor": "system",
                               "action": "생성", "detail": f"{REPRT[str(req['reprt_code'])]['name']} 비교 리포트 생성, 검토 대기"}]},
        "metrics": {
            "changes_by_type": _count(state["changes"], "edit_type"),
            "changes_by_topic": _count(state["changes"], "topic"),
            "relations_by_level": _count(relations, "level"),
            "verification": _count([c["verification"] for c in state["changes"]] + [r["verification"] for r in relations], "status"),
            "verify_rounds": state.get("round", 1),
            "source_calls": getattr(ctx.source, "calls", None),
            "llm_usage": llm_usage,
            "llm_cost_estimate_usd": round(est_cost, 4),
            "llm_cost_note": "LLM 사용 시 추정치(분류 저가 모델 + 최종 보고서 상위 모델). 규칙 모드 실제 비용 0원.",
        },
    }
    return {"report": rep, "_note": f"변경 {len(state['changes'])}건 · 관련 서술 {len(relations)}건 · 표 {len(state['tables'])}개"}


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


NODES = {"ingest": ingest, "numbers": numbers, "diff": diff, "relate": relate, "verify": verify, "report": report}
EDGES = {"ingest": "numbers", "numbers": "diff", "diff": "relate", "relate": "verify", "report": None}


def _builtin_run(state: RadarState) -> RadarState:
    cur = "ingest"
    while cur:
        state = {**state, **NODES[cur](state)}
        cur = route_after_verify(state) if cur == "verify" else EDGES[cur]
    return state


def run_graph(state: RadarState) -> RadarState:
    engine = os.getenv("RADAR_GRAPH", "langgraph")
    if engine == "langgraph":
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            engine = "builtin"
    if engine == "builtin":
        state["_engine"] = "builtin"  # type: ignore[typeddict-unknown-key]
        return _builtin_run(state)

    g = StateGraph(RadarState)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    g.add_edge(START, "ingest")
    for a, b in EDGES.items():
        if b:
            g.add_edge(a, b)
    g.add_conditional_edges("verify", route_after_verify, {"relate": "relate", "report": "report"})
    g.add_edge("report", END)
    final = g.compile().invoke(state, {"recursion_limit": 40})
    final["report"]["meta"]["graph_engine"] = "langgraph"
    return final
