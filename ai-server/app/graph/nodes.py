"""LangGraph 노드 5종: plan(Manager) → disclosure → financial → review ⇄ financial → write.

각 Worker 노드는 두 단계로 일한다.
  ① 결정적 단계 — radar 파이프라인 단계를 돌린다(숫자·인용·검증은 전부 여기서 나온다). 데이터는 Tool Gateway로 읽는다
  ② 서술 단계 — SingleAgent가 Tool을 불러 담당자 메모를 쓴다(LLM). mock이면 관찰 결과 정리로 대신한다
리포트의 숫자와 근거는 ①에서만 온다. ②의 메모는 Report Writer 본문의 재료일 뿐이고, 본문도 Output Filter를 통과해야 나간다.

반려 루프: review가 radar 코드 검증으로 반려된 계정이 있으면 financial로 되돌아가 그 계정만 다시 연결한다.
상한은 AGENT_MAX_REVISIONS(기본 2)이고, 상한에 걸린 계정은 '검토 필요'로 사람에게 넘어간다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agents import prompts
from ..agents.definitions import DISCLOSURE_ANALYST, FINANCIAL_ANALYST, RISK_REVIEWER
from ..config import settings
from ..llm.call_log import LLMCallLogger
from ..llm.factory import active_model_name, get_llm_client
from ..safety.context import set_execution_id, set_job_id
from ..schemas.agent import AgentResult, ToolCallTrace
from ..services.radar_session import sessions
from ..tools.gateway import gateway
from .execution_store import finish_execution, start_execution
from .state import AnalysisState

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
REPRT_NAME = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _call_logger(agent_id: str) -> LLMCallLogger:
    """그래프가 LLM을 직접 부르는 자리(plan·write)용 기록기. Worker는 SingleAgent가 콜백을 단다."""
    return LLMCallLogger(provider=settings.llm_provider, model=active_model_name(), agent_id=agent_id)


def _target_line(state: AnalysisState) -> str:
    t = state["target"]
    return f"[분석 대상] company={t['company']} bsns_year={t['bsns_year']} reprt_code={t['reprt_code']}"


def _session(state: AnalysisState):
    t = state["target"]
    set_job_id(state["job_id"])           # 이 노드에서 부르는 Tool이 같은 분석 세션을 쓰게 한다
    return sessions.open(state["job_id"], t["company"], t["bsns_year"], t["reprt_code"])


def _tool(state: AnalysisState, agent_id: str, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """결정적 단계의 Tool 호출. Agent와 같은 Gateway를 지나므로 Scope 검사와 기록이 똑같이 남는다."""
    result = gateway.invoke(name, params, agent_id=agent_id, user_id=state["user_id"], scope=state["scope"])
    return {"result": result, "trace": ToolCallTrace(tool=name, args=params, agentId=agent_id,
                                                     resultSummary=json.dumps(result, ensure_ascii=False,
                                                                              default=str)[:200]).model_dump()}


async def _worker(state: AnalysisState, *, agent_id: str, step_order: int, input_text: str, body) -> Dict[str, Any]:
    """Worker 하나의 실행을 agent_execution에 RUNNING → COMPLETED/FAILED로 남긴다."""
    exec_id = start_execution(job_id=state["job_id"], request_id=state["request_id"], agent_id=agent_id,
                              step_order=step_order, input_text=input_text)
    set_execution_id(exec_id)             # 이 Worker가 부르는 Tool·LLM 기록이 어느 실행에 속하는지 잇는다
    started = time.time()
    try:
        out, summary = await body()
    except Exception as e:
        finish_execution(exec_id, status="FAILED", duration_ms=int((time.time() - started) * 1000),
                         error_message=f"{type(e).__name__}: {e}")
        raise
    finish_execution(exec_id, status="COMPLETED", output_text=summary, duration_ms=int((time.time() - started) * 1000))
    return out


async def _narrate(agent, state: AnalysisState, task: str) -> AgentResult:
    query = f"{_target_line(state)}\n{task}"
    if state.get("query"):
        query += f"\n관심 질문: {state['query']}"
    return await agent.run(query, user_id=state["user_id"], scope=state["scope"])


# ------------------------------------------------------------------ PLAN (Manager)
async def plan_node(state: AnalysisState) -> Dict[str, Any]:
    known = ["disclosure", "financial"]
    t = state["target"]
    request_text = f"{t['company']} {t['bsns_year']} {REPRT_NAME.get(t['reprt_code'], '')} 전년 대비 비교"
    if state.get("query"):
        request_text += f" / 관심 질문: {state['query']}"

    async def body():
        tasks: Dict[str, str] = {}
        try:
            answer = await get_llm_client().chat(
                [{"role": "user", "content": prompts.MANAGER_PLAN_PROMPT + request_text}],
                config={"callbacks": [_call_logger("manager")]})
            parsed = _extract_json(answer) or {}
            tasks = {k: str(v) for k, v in (parsed.get("tasks") or {}).items() if k in known and v}
        except Exception:
            logger.exception("계획 수립 실패 — 기본 지시로 진행한다")
        # 공시 비교 리포트는 두 담당자가 모두 필요하다. 계획이 비어도 빠뜨리지 않는다
        tasks.setdefault("disclosure", "전년 대비 바뀐 공시 문단 중 중요한 것을 정리하라")
        tasks.setdefault("financial", "계정 증감과 회사가 밝힌 원인, 사업 지표와 시장 지표를 정리하라")
        return {"plan": known, "tasks": tasks}, json.dumps(tasks, ensure_ascii=False)

    return await _worker(state, agent_id="manager", step_order=0, input_text=request_text, body=body)


# -------------------------------------------------------------- DISCLOSURE
async def disclosure_node(state: AnalysisState) -> Dict[str, Any]:
    _session(state)
    task = (state.get("tasks") or {}).get("disclosure", "")
    t = state["target"]

    async def body():
        call = _tool(state, "disclosure_analyst", "compare_filings",
                     {"company": t["company"], "bsns_year": t["bsns_year"], "reprt_code": t["reprt_code"]})
        result = await _narrate(DISCLOSURE_ANALYST, state, task)
        cites = [c["citation"].strip("[]") for c in call["result"].get("topChanges", [])]
        out ={"disclosure": result, "citations": cites + result.citations,
               "tool_calls": [call["trace"]] + [x.model_dump() for x in result.toolCalls]}
        return out, result.answer or json.dumps(call["result"].get("changesByType"), ensure_ascii=False)

    return await _worker(state, agent_id="disclosure_analyst", step_order=1, input_text=task, body=body)


# --------------------------------------------------------------- FINANCIAL
async def financial_node(state: AnalysisState) -> Dict[str, Any]:
    sess = _session(state)
    revision = state.get("revision", 0)
    task = (state.get("tasks") or {}).get("financial", "")
    if revision:
        rejected = (state.get("review") or {}).get("rejected") or []
        task += f"\n검증에서 반려된 계정을 다시 연결했다: {', '.join(rejected) or '없음'}. 바뀐 문장을 확인하라."
    t = state["target"]
    target = {"company": t["company"], "bsns_year": t["bsns_year"], "reprt_code": t["reprt_code"]}

    async def body():
        sess.relate()                                         # 결정적: 관련 서술 연결(반려분만 다시)
        call = _tool(state, "financial_analyst", "get_financial_changes", target)
        calls = [call["trace"]]
        if "MARKET_DATA_READ" in state["scope"] and not revision:
            try:
                calls.append(_tool(state, "financial_analyst", "get_valuation", {"company": t["company"]})["trace"])
            except Exception as e:                            # 시세가 없어도 공시 리포트는 나간다
                logger.info("시장 지표 조회 생략: %s", e)
        result = await _narrate(FINANCIAL_ANALYST, state, task)
        cites = [c.strip("[]") for r in call["result"]["relations"] for c in r["citations"]]
        out = {"financial": result, "citations": cites + result.citations,
               "tool_calls": calls + [x.model_dump() for x in result.toolCalls]}
        levels = [f"{r['account']}:{r['level']}" for r in call["result"]["relations"]]
        return out, result.answer or ", ".join(levels)

    return await _worker(state, agent_id="financial_analyst", step_order=2 + revision * 2, input_text=task, body=body)


# ------------------------------------------------------------------ REVIEW
def draft_text(state: AnalysisState) -> str:
    parts: List[str] = []
    if state.get("disclosure"):
        parts.append("[공시 변경]\n" + state["disclosure"].answer)
    if state.get("financial"):
        parts.append("[수치·서술]\n" + state["financial"].answer)
    return "\n\n".join(parts)


async def review_node(state: AnalysisState) -> Dict[str, Any]:
    sess = _session(state)
    revision = state.get("revision", 0)

    async def body():
        # ① 코드 검증(radar verify) — 인용 ID 존재, 금액·증감률 재계산, 방향, 근거 수준, 소송 교차 확인
        rejected = sess.verify()
        rels = {k: v for k, v in (sess.state.get("relations") or {}).items()}
        rejected_names = [rels[k]["account_nm"] for k in rejected if k in rels]
        issues = [f"코드 검증 반려: {rels[k]['account_nm']} — {rels[k]['attempts'][-1]['reason'][:120]}"
                  for k in rejected if k in rels]
        # ② 규칙 검사 — 담당자 메모(초안)의 표현
        draft = draft_text(state)
        try:
            rule = _tool(state, "risk_reviewer", "check_compliance_rules",
                         {"text": draft, "citation_count": len(state.get("citations") or [])})["result"]
        except PermissionError as e:
            rule = {"passed": True, "issues": [{"message": f"규정 검사 권한이 없다: {e}"}]}
        issues += [f"초안 표현: {i['message']}" for i in rule["issues"]]
        # ③ LLM 검토 — 규칙이 못 잡는 누락(지배구조·소송)
        review_query = (f"{_target_line(state)}\n계획: {state.get('plan')}\n코드 검증 반려: {rejected_names or '없음'}\n"
                        f"규칙 검사가 찾은 문제: {[i['message'] for i in rule['issues']] or '없음'}\n\n{draft[:6000]}")
        result = await RISK_REVIEWER.run(review_query, user_id=state["user_id"], scope=state["scope"])
        verdict = _extract_json(result.answer) or {"passed": True, "issues": []}
        issues += [f"검토자: {x}" for x in verdict.get("issues", [])]

        new_revision = revision
        if rejected and sess.needs_revision() and revision < settings.agent_max_revisions:
            new_revision, next_step = revision + 1, "revise"    # 반려된 계정만 다시 연결한다
        else:
            next_step = "write"
        passed = not rejected and bool(rule["passed"]) and bool(verdict.get("passed", True))
        out = {"review": {"passed": passed, "issues": issues, "nextStep": next_step, "rejected": rejected_names},
               "revision": new_revision, "tool_calls": [x.model_dump() for x in result.toolCalls]}
        return out, (f"반려 {len(rejected)}건 → 재연결" if next_step == "revise" else
                     f"검토 완료 · 지적 {len(issues)}건")

    return await _worker(state, agent_id="risk_reviewer", step_order=3 + revision * 2,
                         input_text=f"revision={revision}", body=body)


def route_after_review(state: AnalysisState) -> str:
    return "financial" if (state.get("review") or {}).get("nextStep") == "revise" else "write"


# ------------------------------------------------------------------- WRITE
def _facts(rep: Dict[str, Any]) -> str:
    """Report Writer에게 주는 [검증된 사실]. 전부 radar가 코드로 만들고 검증한 값이다."""
    lines = [rep.get("summary") or ""]
    for c in (rep.get("changes") or [])[:6]:
        ref = (c["new"] or c["old"])[0]["pid"] if (c["new"] or c["old"]) else ""
        lines.append(f"- [{c['topic']}·{c['edit_type']}] {c['summary']} [{ref}]")
    for r in rep.get("relations") or []:
        ref = r["evidence"][0]["pid"] if r.get("evidence") else ""
        lines.append(f"- {r['statement']}" + (f" [{ref}]" if ref else ""))
    for g in ((rep.get("governance") or {}).get("changes") or [])[:5]:
        lines.append(f"- 지배구조({g.get('kind')}): {g.get('text')} [dart:{rep['meta']['current']['rcept_no']}]")
    return "\n".join(x for x in lines if x)


async def write_node(state: AnalysisState) -> Dict[str, Any]:
    sess = _session(state)
    review = state.get("review") or {}

    async def body():
        rep = sess.finalize()                               # radar Report Writer: 계약 JSON(docs/report.schema.json)
        facts = _facts(rep)
        evidence = [e["pid"] for r in rep.get("relations") or [] for e in r.get("evidence", [])]
        citations = list(dict.fromkeys((state.get("citations") or []) + evidence))
        writer_input = (f"{_target_line(state)}\n관심 질문: {state.get('query') or '없음'}\n\n"
                        f"{draft_text(state)[:6000]}\n\n사용할 수 있는 인용: {citations}\n"
                        f"검토자 지적: {review.get('issues') or '없음'}\n\n[검증된 사실]\n{facts}")
        try:
            text = await get_llm_client().chat(
                [{"role": "system", "content": prompts.REPORT_WRITER_SYSTEM}, {"role": "user", "content": writer_input}],
                config={"callbacks": [_call_logger("report_writer")]})
        except Exception as e:                              # 본문 작성 실패는 리포트 실패가 아니다 — 사실 목록으로 대신한다
            logger.warning("본문 작성 실패: %s", e)
            text = facts
        m = rep["meta"]
        rep.update({
            "title": rep.get("title") or f"{m['company']['corp_name']} {m['prior']['report_nm']} → {m['current']['report_nm']} 비교",
            "body": text,
            "citations": citations,
            "toolCalls": state.get("tool_calls") or [],
            "reviewPassed": bool(review.get("passed", True)) and bool(rep.get("reviewPassed", True)),
            "reviewIssues": list(dict.fromkeys((rep.get("reviewIssues") or []) + (review.get("issues") or []))),
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return {"report": rep}, text[:4000]

    return await _worker(state, agent_id="report_writer", step_order=9, input_text="write", body=body)
