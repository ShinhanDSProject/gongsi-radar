"""고정 DAG 파이프라인.

  수집·파싱 → 수치 분석 → 본문 비교 → 관련 서술 연결 → 검증 ─(통과)→ Report Writer
                                         ↑                 │
                                         └──(반려, 최대 2회)─┘

분석 1건의 순서는 항상 같으므로 Manager가 워커를 고르지 않는다. 동적으로 갈라지는 곳은 검증 반려 루프 하나다.
LangGraph가 설치되어 있으면 StateGraph로, 없으면 같은 토폴로지의 내장 러너로 실행한다(RADAR_GRAPH=builtin으로 강제).

노드별 확장(§6): ingest가 지배구조(당기·전기)·시장 지표 원자료(최근 연간·중간 재무, 시세)까지 모으고,
numbers가 계정 계산식(accounts[].formulas)·지배구조·시장 지표를, diff가 사업 지표(검산 포함)를 만든다.

AI 서버(LangGraph 워커)에서 단계별로 부르는 법 — 노드 함수는 RadarState dict를 받아 '갱신분'만 돌려준다:

    from radar.graph import prepare_context, initial_state, apply, ingest, numbers, diff, relate, verify, \
        report, route_after_verify, finalize
    ctx = prepare_context(settings, request)          # request: {company, bsns_year, reprt_code, demo_fault_injection?, as_of?}
    state = initial_state(ctx, request)
    state = apply(state, ingest)                      # disclosure_analyst
    state = apply(state, numbers)                     # financial_analyst
    state = apply(state, diff)                        # disclosure_analyst
    while True:
        state = apply(state, relate)
        state = apply(state, verify)                  # risk_reviewer
        if route_after_verify(state) == "report":
            break
    state = apply(state, report)                      # report_writer
    rep = finalize(state)                             # timeline·소요 시간을 붙이고 스키마 검증한 RadarReport dict

노드 순서·이름을 바꾸면 타임라인과 테스트가 깨진다. 노드는 서로의 갱신분에만 의존하므로 순서만 지키면 된다.
"""
from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TypedDict

from . import financials as finmod
from .align import diff_documents, number_changes, word_diff
from .classify import INJECTION_SUMMARY, importance, injection_suspected, topic_of
from .business import extract_business
from .config import ALIGN_THRESHOLDS, MAX_VERIFY_RETRIES, PIPELINE_VERSION, RELATE_SECTIONS, Settings
from .embed import kind_of, make_embedder
from .formula import texts
from .governance import build_governance, known_names
from .llm import PRICE_PER_M, RuleLLM, make_llm
from .parser import ParsedDoc, parse_filing_zip
from .relate import direction, numeric_claims, rule_relate, top_candidates_for_llm
from .sources import REPRT, SourceError, make_source
from .tables import diff_tables
from .textutil import josa, norm_ws
from .valuation import gather_valuation_inputs, valuation_from_inputs
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
    # 확장(§6)
    gov_raw: dict          # {"current": source.governance(...), "prior": ...|None}
    known: dict            # 회사 목록 {정규화 이름: corp_code}
    valuation_inputs: dict  # valuation.gather_valuation_inputs 결과
    governance: dict | None
    valuation: dict | None
    business: dict | None
    extra_notes: list      # 확장 데이터 수집 실패 사유


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
    # 확장 데이터: 없거나 실패해도 분석은 계속한다(리포트에 사유를 남김)
    extra: list[str] = []
    gov_raw = {"current": None, "prior": None}
    for side, y in (("current", year), ("prior", year - 1)):
        try:
            gov_raw[side] = src.governance(company["corp_code"], y, code)
        except (SourceError, AttributeError) as e:
            extra.append(f"지배구조({y}): {e}")
    try:
        known = known_names([c for c in src.companies() if c["corp_code"] != company["corp_code"]])
    except (SourceError, AttributeError):
        known = {}
    try:
        vi = gather_valuation_inputs(src, company, req.get("as_of"))  # as_of 없으면 오늘 기준(최근 시세)
    except (SourceError, AttributeError) as e:
        vi = {"annual": None, "notes": [f"시장 지표 원자료 수집 실패: {e}"]}
    gov_n = sum(1 for v in gov_raw.values() if v)
    mk = f"시세 {len(vi.get('prices') or [])}일" + (", 중간 재무 " + REPRT[vi["interim"]["reprt_code"]]["name"]
                                                 if vi.get("interim") else "")
    return {"company": company, "filings": {"current": cur, "prior": prior}, "docs": docs, "fin_rows": fin_rows,
            "fs_div": fs_div, "peers": peers, "lawsuits": lawsuits,
            "gov_raw": gov_raw, "known": known, "valuation_inputs": vi, "extra_notes": extra,
            "_note": f"원문 2건 파싱(본문 {d.chosen_file}, {d.encoding_used}), 재무 {fs_div}, "
                     f"피어 {len({p.get('corp_code') for p in peers})}개사, 지배구조 {gov_n}건, {mk}"}


@node("numbers")
def numbers(state: RadarState) -> dict:
    accts = finmod.account_changes(state["fin_rows"], state["request"]["reprt_code"])
    finmod.add_flags(accts, state["peers"])
    finmod.explain_accounts(accts, state["fs_div"], state["peers"])
    targets = finmod.targets(accts)
    flagged = sum(1 for a in accts if a["flags"])
    raw = state.get("gov_raw") or {}
    gov = build_governance(raw["current"], raw.get("prior"), state.get("known"), state["company"]) \
        if raw.get("current") else None
    val = valuation_from_inputs(state.get("valuation_inputs") or {})
    vnote = "시장 지표 없음"
    if val:
        done = sum(1 for m in val["metrics"] if m["status"] == "계산됨")
        vnote = f"시장 지표 {done}/{len(val['metrics'])}개 계산"
    gnote = f"지배구조 변동 {len(gov['changes'])}건" if gov else "지배구조 없음"
    return {"accounts": accts, "targets": [t["key"] for t in targets], "governance": gov, "valuation": val,
            "_note": f"계정 {len(accts)}개 증감 계산, 플래그 {flagged}개, 관련 서술 연결 대상 {len(targets)}개 | {gnote} | {vnote}"}


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
    rev = next((a for a in state.get("accounts") or [] if a["account_nm"] in ("매출액", "수익(매출액)", "영업수익")), None)
    f = state["filings"]
    business = extract_business(old, new, {"prior": rev["prior"], "current": rev["current"]} if rev else None,
                                (int(f["prior"]["bsns_year"]), int(f["current"]["bsns_year"])))
    bs = business["summary"]
    return {"changes": items, "tables": tables, "business": business,
            "_note": " · ".join(f"{k} {v}" for k, v in by.items()) + f" | 표 {len(tables)}개 | 중복 제거 {dup}건 | 지시문 의심 {inj}건"
                     + f" | 사업 지표 {len(business['groups'])}종 검산 통과 {bs['passed']}·불일치 {bs['failed']}·불가 {bs['unchecked']}"}


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
    business, governance, valuation = state.get("business"), state.get("governance"), state.get("valuation")
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
            "extra_notes": list(state.get("extra_notes") or []),
        },
        "business": business, "governance": governance, "valuation": valuation,
    }
    issues, passed = review_issues(rep)
    rep.update({
        "title": f"{state['company']['corp_name']} {cur['report_nm']} 전년 대비 공시 비교",
        "summary": overview_sentence(rep),
        "citations": citations(rep),
        "toolCalls": [], "agents": [],  # AI 서버(에이전트 계층)가 채운다
        "reviewPassed": passed, "reviewIssues": issues,
        "generatedAt": rep["meta"]["created_at"],
    })
    return {"report": rep, "_note": f"변경 {len(state['changes'])}건 · 관련 서술 {len(relations)}건 · 표 {len(state['tables'])}개"
                                    + f" · 검토 항목 {len(issues)}건"}


def overview_sentence(rep: dict) -> str:
    """리포트 개요 한 문단(web/src/lib.js overviewSentence와 같은 규칙)."""
    n = len(rep["changes"])
    by_topic = rep["metrics"].get("changes_by_topic") or {}
    parts = [f"변경 문단 {n}건 중 위험·소송 {by_topic.get('위험·소송', 0)}건, 거래 {by_topic.get('거래', 0)}건입니다."]
    names = {lv: "·".join(r["account_nm"] for r in rep["relations"] if r["level"] == lv)
             for lv in ("인과 명시", "관련 맥락", "확인 불가")}
    if names["인과 명시"]:
        parts.append(f"{names['인과 명시']}{josa(names['인과 명시'], '은는')} 회사가 원인을 직접 밝혔습니다.")
    if names["관련 맥락"]:
        parts.append(f"{names['관련 맥락']}{josa(names['관련 맥락'], '은는')} 관련 서술만 있고 원인은 밝히지 않았습니다.")
    if names["확인 불가"]:
        parts.append(f"{names['확인 불가']} 변화는 본문에서 관련 서술을 찾지 못했습니다.")
    return " ".join(parts)


def citations(rep: dict) -> list[str]:
    """인용 목록: dart:접수번호 · 인용 문단 ID · market-data:종목코드 (순서 유지, 중복 제거)."""
    out = [f"dart:{rep['meta']['current']['rcept_no']}", f"dart:{rep['meta']['prior']['rcept_no']}"]
    for r in rep["relations"]:
        out += [e["pid"] for e in r["evidence"]]
    for c in rep["changes"]:
        out += [x["pid"] for x in c["old"] + c["new"]]
    for g in (rep.get("business") or {}).get("groups", []):
        out += [p for p in (g["priorPid"], g["currentPid"]) if p]
    v = rep.get("valuation")
    if v and v.get("price"):
        out.append(f"market-data:{rep['meta']['company'].get('stock_code', '')}")
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def review_issues(rep: dict) -> tuple[list[str], bool]:
    """(사람이 볼 항목, 코드 검증 통과 여부).

    reviewPassed는 '자동 검증을 통과했는가'다: 반려 상태로 남은 항목이 없고, 생성한 모든 문구가 출력 필터를 통과.
    검토 필요 항목(지시문 의심·재실행 상한 도달)과 사업 지표 검산 불일치는 통과 여부와 별개로 reviewIssues에 남긴다.
    """
    issues, failed = [], False
    for c in rep["changes"]:
        st = c["verification"]["status"]
        if st in ("검토 필요", "반려"):
            why = [k["name"] for k in c["verification"]["checks"] if k["status"] != "pass"] or c["flags"]
            issues.append(f"{c['id']} {st}: {', '.join(why)}")
            failed |= st == "반려"
    for r in rep["relations"]:
        st = r["verification"]["status"]
        if st in ("검토 필요", "반려"):
            issues.append(f"{r['account_nm']} 관련 서술 {st}: {r['attempts'][-1]['reason'] if r['attempts'] else ''}")
            failed |= st == "반려"
    for g in (rep.get("business") or {}).get("groups", []):
        for row in g["rows"]:
            if row["status"] == "검산 불일치":
                bad = [k["detail"] for k in row["checks"] if k["status"] == "fail"]
                issues.append(f"사업 지표 검산 불일치({g['kind']} · {row['label']}): {'; '.join(bad)}")
        for k in g["checks"]:
            if k["status"] == "fail":
                issues.append(f"사업 지표 대조 실패({g['kind']} · {k['name']}): {k['detail']}")
    generated = [c["summary"] for c in rep["changes"]] + [r["statement"] for r in rep["relations"]]
    generated += texts([rep.get("business"), rep.get("governance"), rep.get("valuation"),
                        [a.get("formulas") for a in rep["accounts"]]])
    hits = sorted({h for t in generated for h in banned_hits(t)})
    if hits:
        issues.append(f"출력 필터: {', '.join(hits)}")
    return issues, not failed and not hits


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


# ---- 단계별 호출(AI 서버 워커용) ---------------------------------------------------------
def new_id() -> str:
    return datetime.now().strftime("A%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def prepare_context(settings: Settings | None = None, request: dict | None = None, on_event=None,
                    analysis_id: str | None = None, request_uid: str | None = None, source=None) -> Ctx:
    """노드가 쓰는 Ctx(소스·임베더·LLM). request의 demo_fault_injection을 설정에 반영한다.

    source를 주면 그대로 쓴다(AI 서버가 Tool Gateway 쪽 소스를 공유할 때).
    """
    s = settings or Settings()
    if request and "demo_fault_injection" in request:
        s.demo_fault_injection = bool(request["demo_fault_injection"])
    return Ctx(settings=s, source=source or make_source(s), embedder=make_embedder(s.embedder), llm=make_llm(s),
               on_event=on_event or (lambda e: None), analysis_id=analysis_id or new_id(), request_uid=request_uid)


def initial_state(ctx: Ctx, request: dict) -> RadarState:
    return {"ctx": ctx, "request": request, "timeline": [], "round": 0}


def apply(state: RadarState, node_fn) -> RadarState:
    """노드 하나를 실행하고 갱신분을 합친 새 state를 돌려준다(LangGraph의 상태 병합과 같음)."""
    return {**state, **node_fn(state)}


def finalize(state: RadarState) -> dict:
    """report 노드 뒤: 타임라인·소요 시간을 붙이고 계약(schemas.Report)으로 검증한 리포트."""
    from .schemas import Report

    rep = state["report"]
    rep["timeline"] = state["timeline"]
    rep["metrics"]["elapsed_ms"] = state["timeline"][-1]["ended_ms"]
    Report.model_validate(rep)  # 계약 위반이면 여기서 실패
    return rep


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
