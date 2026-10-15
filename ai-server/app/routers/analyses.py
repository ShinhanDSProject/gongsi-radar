from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from ..agents.runner import run_analysis
from ..deps import verify_internal_key
from ..graph.execution_store import list_executions
from ..safety import kill_switch
from ..safety.audit import record_guardrail
from ..safety.context import set_request_uid
from ..safety.input_filter import check_input
from ..schemas.analysis import AnalysisRequest, JobStatus
from ..services.job_store import job_store

router = APIRouter(prefix="/ai", tags=["analyses"])


@router.post("/analyses", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(verify_internal_key)])
async def start_analysis(req: AnalysisRequest, background: BackgroundTasks,
                         x_request_id: str = Header(default="")) -> JobStatus:
    # ① 상관관계 ID를 먼저 심는다. 이후 모든 기록이 이 값을 달고 남는다
    request_uid = set_request_uid(x_request_id or None)
    # ② Kill Switch(DB 상태)
    active, reason = kill_switch.status()
    if active:
        raise HTTPException(status_code=503, detail={"error": "KILL_SWITCH_ACTIVE", "reason": reason})
    # ③ Input Filter — 관심 질문과 회사 입력. LLM에 닿기 전이다. 여기서 막히면 Agent는 시작조차 하지 않는다
    text = " ".join(x for x in (req.company, req.query or "") if x)
    guard = check_input(text)
    record_guardrail("INPUT", guard, text, user_id=req.userId, request_id=req.requestId)
    if guard.shouldBlock:
        raise HTTPException(status_code=422, detail={"error": "GUARDRAIL_BLOCKED",
                                                     "detectedIssues": guard.detectedIssues, "requestUid": request_uid})
    query = check_input(req.query).filteredText if req.query else None   # 마스킹을 마친 것만 Agent로 넘긴다
    job = job_store.create()
    # BackgroundTasks는 별도 컨텍스트에서 돈다. request_uid를 인자로 넘겨 다시 심는다
    background.add_task(run_analysis, job.jobId, req, query, request_uid)
    return job


@router.get("/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(verify_internal_key)])
async def get_job(job_id: str) -> JobStatus:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.agentExecutions = list_executions(job_id)
    return job
