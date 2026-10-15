"""Worker 실행 이력을 agent_execution 테이블에 기록한다.
tools/db.py의 앱 계정 엔진을 쓴다(업무 기록이라 감사 계정이 아니다).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from ..config import settings
from ..llm.factory import active_model_name
from ..tools.db import get_engine

logger = logging.getLogger(__name__)


def start_execution(*, job_id: str, request_id: int, agent_id: str,
                    step_order: int, input_text: str) -> Optional[int]:
    """Worker 시작 시 RUNNING 행을 넣고 id를 돌려준다."""
    try:
        with get_engine().begin() as conn:
            res = conn.execute(sa.text("""
                INSERT INTO agent_execution
                    (request_id, job_id, agent_id, step_order, status,
                     input_text, model_provider, model_name, started_at)
                VALUES
                    (:request_id, :job_id, :agent_id, :step_order, 'RUNNING',
                     :input_text, :provider, :model, :started_at)
            """), {
                "request_id": request_id, "job_id": job_id, "agent_id": agent_id,
                "step_order": step_order, "input_text": input_text[:4000],
                "provider": settings.llm_provider, "model": active_model_name(),
                "started_at": datetime.now(timezone.utc),
            })
            return res.lastrowid
    except Exception:
        # [주의] 기록이 실패해도 분석은 계속 진행한다
        logger.exception("agent_execution 기록 실패: job=%s agent=%s", job_id, agent_id)
        return None


def finish_execution(execution_id: Optional[int], *, status: str,
                     output_text: str = "", duration_ms: int = 0,
                     error_message: Optional[str] = None) -> None:
    if execution_id is None:
        return
    try:
        with get_engine().begin() as conn:
            conn.execute(sa.text("""
                UPDATE agent_execution
                   SET status=:status, output_text=:output_text,
                       duration_ms=:duration_ms, error_message=:error_message,
                       finished_at=:finished_at
                 WHERE id=:id
            """), {
                "id": execution_id, "status": status,
                "output_text": (output_text or "")[:60000],
                "duration_ms": duration_ms, "error_message": error_message,
                "finished_at": datetime.now(timezone.utc),
            })
    except Exception:
        logger.exception("agent_execution 갱신 실패: id=%s", execution_id)


def list_executions(job_id: str) -> List[Dict[str, Any]]:
    """폴링 응답에 실을 요약. 순서대로 돌려준다."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(sa.text("""
                SELECT agent_id, step_order, status, duration_ms, error_message, output_text
                  FROM agent_execution
                 WHERE job_id = :job_id
                 ORDER BY step_order, id
            """), {"job_id": job_id}).all()
    except Exception:
        logger.exception("agent_execution 조회 실패: job=%s", job_id)
        return []

    return [
        {
            "agentId": r.agent_id,
            "stepOrder": r.step_order,
            "status": r.status,
            "durationMs": r.duration_ms,
            "errorMessage": r.error_message,
            # 화면 타임라인용 한 줄 요약. 전문은 DB에만 둔다
            "summary": (r.output_text or "")[:160] or None,
        }
        for r in rows
    ]
