"""분석 실행(백그라운드). 그래프 앞뒤에 상관관계 ID 재설정·Output Filter·감사 기록을 붙인다."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..graph.build import get_analysis_graph
from ..safety.audit import record_audit, record_guardrail
from ..safety.context import set_job_id, set_request_uid
from ..safety.output_filter import filter_report
from ..schemas.analysis import AnalysisRequest
from ..services.job_store import job_store
from ..services.radar_session import sessions

logger = logging.getLogger(__name__)

# 노드가 끝났을 때의 진행률과 다음 단계 이름
_AFTER = {"plan": (0.1, "DISCLOSURE"), "disclosure": (0.4, "FINANCIAL"), "financial": (0.6, "REVIEW"),
          "write": (0.98, "DONE")}


async def run_analysis(job_id: str, req: AnalysisRequest, query: Optional[str],
                       request_uid: Optional[str] = None) -> None:
    # 백그라운드 태스크는 새 컨텍스트에서 시작한다. 라우터가 심은 contextvar가 따라오지 않으므로 다시 심는다
    set_request_uid(request_uid)
    set_job_id(job_id)
    sessions.open(job_id, req.company, req.bsnsYear, req.reprtCode,
                  demo_fault_injection=req.options.demoFaultInjection, request_id=req.requestId)
    initial: Dict[str, Any] = {
        "job_id": job_id, "request_id": req.requestId, "user_id": req.userId, "scope": req.scope,
        "target": {"company": req.company, "bsns_year": req.bsnsYear, "reprt_code": req.reprtCode},
        "query": query, "citations": [], "tool_calls": [], "revision": 0,
    }
    report: Optional[Dict[str, Any]] = None
    job_store.update(job_id, currentStep="PLANNING")
    try:
        async for chunk in get_analysis_graph().astream(initial):
            for node_name, node_out in chunk.items():
                if node_name == "review":
                    nxt = "FINANCIAL" if (node_out or {}).get("review", {}).get("nextStep") == "revise" else "WRITING"
                    job_store.update(job_id, progress=0.8, currentStep=nxt)
                else:
                    progress, nxt = _AFTER.get(node_name, (0.5, None))
                    job_store.update(job_id, progress=progress, currentStep=nxt)
                if node_name == "write":
                    report = (node_out or {}).get("report")
    except Exception as e:
        logger.exception("그래프 실행 실패: job=%s", job_id)
        job_store.update(job_id, status="FAILED", progress=1.0, currentStep="FAILED",
                         result={"error": f"{type(e).__name__}: {e}"})
        record_audit("AGENT_EXECUTION", user_id=req.userId, request_id=req.requestId,
                     payload={"jobId": job_id, "status": "FAILED", "error": type(e).__name__})
        sessions.drop(job_id)
        return

    if report is None:
        job_store.update(job_id, status="FAILED", progress=1.0, currentStep="FAILED",
                         result={"error": "리포트를 만들지 못했다"})
        sessions.drop(job_id)
        return

    # Output Filter — 사용자에게 나가는 마지막 한 지점. 반려 루프가 몇 번을 돌든 여기서 한 번 본다
    filtered, guard = filter_report(report)
    record_guardrail("OUTPUT", guard, report.get("body") or "", user_id=req.userId, agent_id="report_writer",
                     request_id=req.requestId)
    record_audit("AGENT_EXECUTION", user_id=req.userId, request_id=req.requestId,
                 payload={"jobId": job_id, "status": "COMPLETED", "riskLevel": guard.riskLevel,
                          "rcept_no": [report["meta"]["prior"]["rcept_no"], report["meta"]["current"]["rcept_no"]],
                          "citations": len(report.get("citations") or []), "reviewPassed": report.get("reviewPassed")})
    job_store.update(job_id, status="COMPLETED", progress=1.0, currentStep="DONE", result={"report": filtered})
    sessions.drop(job_id)          # 리포트 정본은 Spring이 저장한다. 파싱한 문서는 메모리에 오래 두지 않는다
