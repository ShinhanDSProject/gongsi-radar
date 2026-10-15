"""FastAPI AI Layer (팀 표준 스택). 실행: uvicorn radar.api:app --port 8000  또는  python -m radar serve

실제 아키텍처에서 브라우저는 Spring Boot만 호출하고, Spring이 내부 API Key와 X-Request-UID를 붙여 이 API를
부른다. 프로토타입은 단독 시연을 위해 검토(HITL)·감사 로그·Kill Switch 엔드포인트도 함께 둔다.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import PIPELINE_VERSION
from .service import ReviewError, Service
from .webui import index_html

svc = Service()
app = FastAPI(title="공시레이더 AI Layer (prototype)", version=PIPELINE_VERSION)


def internal_key(x_internal_key: str | None = Header(default=None)):
    """RADAR_INTERNAL_KEY가 설정되면 Spring→FastAPI 호출에 같은 키를 요구한다."""
    want = os.getenv("RADAR_INTERNAL_KEY")
    if want and x_internal_key != want:
        raise HTTPException(401, "내부 API Key가 필요합니다.")


class AnalysisIn(BaseModel):
    company: str = Field("999001", description="종목코드, 고유번호 또는 회사명")
    bsns_year: int = 2025
    reprt_code: Literal["11011", "11012", "11013", "11014"] = "11011"
    demo_fault_injection: bool = False


class EditIn(BaseModel):
    item_id: str
    value: str


class ReviewIn(BaseModel):
    reviewer: str
    action: Literal["approve", "request_changes", "edit"] = "edit"
    comment: str | None = None
    edits: list[EditIn] = []


class KillIn(BaseModel):
    on: bool
    actor: str = "admin"


def _err(e: Exception):
    if isinstance(e, ReviewError):
        raise HTTPException(e.code, str(e))
    if isinstance(e, KeyError):
        raise HTTPException(404, f"없는 분석: {e}")
    raise e


@app.post("/api/analyses", status_code=202, dependencies=[Depends(internal_key)])
def create_analysis(body: AnalysisIn, x_request_uid: str | None = Header(default=None)):
    try:
        return svc.start(body.model_dump(), x_request_uid)
    except Exception as e:  # noqa: BLE001
        _err(e)


@app.get("/api/analyses", dependencies=[Depends(internal_key)])
def list_analyses():
    return svc.store.list()


@app.get("/api/analyses/{aid}", dependencies=[Depends(internal_key)])
def analysis_status(aid: str):
    try:
        return svc.status(aid)
    except Exception as e:  # noqa: BLE001
        _err(e)


@app.get("/api/analyses/{aid}/report", dependencies=[Depends(internal_key)])
def analysis_report(aid: str):
    try:
        return svc.store.load(aid)
    except Exception as e:  # noqa: BLE001
        _err(e)


@app.get("/api/analyses/{aid}/audit", dependencies=[Depends(internal_key)])
def analysis_audit(aid: str):
    return svc.store.audit_for(aid)


@app.post("/api/analyses/{aid}/review", dependencies=[Depends(internal_key)])
def analysis_review(aid: str, body: ReviewIn):
    try:
        return svc.review(aid, body.model_dump())
    except Exception as e:  # noqa: BLE001
        _err(e)


@app.get("/api/admin/kill-switch", dependencies=[Depends(internal_key)])
def kill_status():
    return {"on": svc.store.killed()}


@app.post("/api/admin/kill-switch", dependencies=[Depends(internal_key)])
def kill_set(body: KillIn):
    return {"on": svc.store.set_kill(body.on, body.actor)}


@app.get("/", response_class=HTMLResponse)
def index():
    return index_html(None)
