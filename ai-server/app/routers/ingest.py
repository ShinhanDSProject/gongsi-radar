"""일일 수집(#3) 상태 — 관리 화면용. 적재 DB를 앱 계정으로 읽기만 한다(수집 실행은 이 서버가 하지 않는다).

수집은 별도 작업(`python -m radar ingest daily`, cron)이 수집 전용 계정으로 한다. AI 서버가 수집을 시작하게 두지 않는 이유:
원천 API 키와 쓰기 권한을 요청을 받는 서버에 두지 않기 위해서다(Core Zone 시스템 키를 이 서버에 두지 않은 것과 같은 판단).
"""
import os
from datetime import datetime, time

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header

from radar.ingest import tables as T
from radar.ingest.store import IngestStore

from ..deps import verify_internal_key
from ..safety.context import set_request_uid
from ..tools.db import get_engine

router = APIRouter(prefix="/ai/ingest", tags=["ingest"])


@router.get("/status", dependencies=[Depends(verify_internal_key)])
def status(x_request_id: str = Header(default="")) -> dict:
    set_request_uid(x_request_id or None)
    budget = int(os.getenv("INGEST_DAILY_BUDGET", "15000"))
    store = IngestStore(get_engine())
    try:
        runs = store.recent_runs(200)
        tables = {t.name: store.count(t) for t in (T.company, T.filing, T.financial_line, T.market_daily, T.index_daily)}
        with store.engine.connect() as conn:
            last_market = conn.execute(sa.select(sa.func.max(T.market_daily.c.bas_dt))).scalar()
    except sa.exc.SQLAlchemyError as e:
        return {"enabled": False, "reason": f"적재 테이블을 읽지 못했습니다({type(e).__name__}). scripts/sql/07_ingest_schema.sql 적용 여부를 확인하세요.",
                "runs": [], "steps": [], "tables": {}, "budget": budget}
    if not runs:
        return {"enabled": True, "reason": "아직 수집을 한 번도 돌리지 않았습니다(python -m radar ingest daily).",
                "runs": [], "steps": [], "tables": tables, "budget": budget, "callsToday": 0, "budgetLeft": budget}
    midnight = datetime.combine(datetime.now().date(), time.min)
    calls_today = sum(r["calls"] for r in runs if r["started_at"] >= midnight)
    last_uid = runs[0]["run_uid"]
    steps = [r for r in runs if r["run_uid"] == last_uid]
    by_run: dict[str, dict] = {}
    for r in runs:
        g = by_run.setdefault(r["run_uid"], {"runUid": r["run_uid"], "mode": r["mode"], "source": r["source"],
                                             "startedAt": r["started_at"], "finishedAt": r["finished_at"],
                                             "calls": 0, "rows": 0, "statuses": []})
        g["calls"] += r["calls"]
        g["rows"] += r["rows_written"]
        g["statuses"].append(r["status"])
        g["startedAt"] = min(g["startedAt"], r["started_at"])
        if r["finished_at"] and (not g["finishedAt"] or r["finished_at"] > g["finishedAt"]):
            g["finishedAt"] = r["finished_at"]
    def overall(sts):
        for s in ("FAILED", "SKIPPED", "PARTIAL", "RUNNING"):
            if s in sts:
                return s
        return "DONE"
    run_rows = [{**{k: v for k, v in g.items() if k != "statuses"}, "status": overall(g["statuses"])}
                for g in list(by_run.values())[:10]]
    return {
        "enabled": True, "reason": None, "budget": budget, "callsToday": calls_today,
        "budgetLeft": max(0, budget - calls_today), "lastMarketDate": last_market, "tables": tables,
        "lastRun": run_rows[0], "runs": run_rows,
        "steps": [{"step": r["step"], "status": r["status"], "calls": r["calls"], "rows": r["rows_written"],
                   "remaining": r["remaining"], "error": r["error_message"], "finishedAt": r["finished_at"]}
                  for r in reversed(steps)],
    }
