"""Manager-Worker 그래프 회귀 테스트(LLM_PROVIDER=mock, 샘플 데이터).
계획 → 공시 비교 → 재무 → 검토 ⇄ 재무 → 작성 순서, 반려 루프, 실행·Tool 기록, 인용 격리를 본다.
"""
import asyncio

import pytest
import sqlalchemy as sa

from app.agents.runner import run_analysis
from app.graph.execution_store import list_executions
from app.schemas.analysis import AnalysisOptions, AnalysisRequest
from app.services.job_store import job_store
from radar.verify import banned_hits

SCOPE = ["DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ", "REPORT_READ"]


def _run(fault: bool, scope=SCOPE):
    req = AnalysisRequest(requestId=7, userId="analyst_001", company="999001", bsnsYear=2025, reprtCode="11011",
                          query="소송 관련 변화 중심으로", scope=scope, options=AnalysisOptions(demoFaultInjection=fault))
    job = job_store.create()
    asyncio.run(run_analysis(job.jobId, req, req.query, f"req-pytest-{job.jobId[:8]}"))
    return job.jobId, job_store.get(job.jobId)


@pytest.fixture(scope="module")
def fault_run():
    return _run(fault=True)


def test_graph_runs_all_workers_with_reject_loop(fault_run):
    job_id, job = fault_run
    assert job.status == "COMPLETED" and job.currentStep == "DONE"
    agents = [e["agentId"] for e in list_executions(job_id)]
    assert agents == ["manager", "disclosure_analyst", "financial_analyst", "risk_reviewer",
                      "financial_analyst", "risk_reviewer", "report_writer"]
    rep = job.result["report"]
    op = next(r for r in rep["relations"] if r["account_nm"] == "영업이익")
    assert [a["status"] for a in op["attempts"]] == ["반려", "통과"]
    assert rep["reviewPassed"] is True


def test_report_wrapper_fields_and_citations(fault_run):
    _, job = fault_run
    rep = job.result["report"]
    assert rep["title"] and rep["body"] and rep["generatedAt"]
    assert rep["citations"]
    inj = next(c for c in rep["changes"] if "지시문 의심" in c["flags"])
    assert inj["new"][0]["pid"] not in rep["citations"]          # 지시문 의심 문단은 근거가 아니다
    assert {t["tool"] for t in rep["toolCalls"]} >= {"compare_filings", "get_financial_changes"}
    for text in [rep["body"]] + [c["summary"] for c in rep["changes"]] + [r["statement"] for r in rep["relations"]]:
        assert banned_hits(text) == [], text
    assert rep["guardrail"]["riskLevel"] in ("SAFE", "WARNING")


def test_tool_calls_are_linked_to_executions(fault_run, record_db):
    job_id, _ = fault_run
    with record_db.connect() as conn:
        rows = conn.execute(sa.text("""SELECT t.tool_name, e.agent_id FROM agent_tool_call_log t
                                       JOIN agent_execution e ON e.id = t.execution_id WHERE e.job_id = :j"""),
                            {"j": job_id}).all()
    assert {(r.tool_name, r.agent_id) for r in rows} >= {("compare_filings", "disclosure_analyst"),
                                                         ("get_financial_changes", "financial_analyst"),
                                                         ("check_compliance_rules", "risk_reviewer")}


def test_without_market_scope_report_still_completes(record_db):
    """시세 권한이 없으면 시장 지표 조회를 시도하지 않고, 공시 비교 리포트는 그대로 나간다."""
    job_id, job = _run(fault=False, scope=["DISCLOSURE_READ", "RAG_READ", "REPORT_READ"])
    assert job.status == "COMPLETED"
    assert "get_valuation" not in {t["tool"] for t in job.result["report"]["toolCalls"]}
    with record_db.connect() as conn:
        tools = {r.tool_name for r in conn.execute(sa.text(
            """SELECT t.tool_name FROM agent_tool_call_log t JOIN agent_execution e ON e.id = t.execution_id
               WHERE e.job_id = :j AND t.scope_pass = 1"""), {"j": job_id})}
    assert "get_valuation" not in tools and "compare_filings" in tools
