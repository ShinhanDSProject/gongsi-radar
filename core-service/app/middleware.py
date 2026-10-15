"""응답 지연 · 의도적 실패 · 감사 기록.

셋 다 운영 환경을 흉내내기 위한 장치다. 지연과 실패는 AI Layer의 타임아웃·재시도가
실제로 도는지 보려고 넣었고, 감사는 Core Zone이 자기 앞으로 온 호출을 스스로 남기기 위한 것이다.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import random
import time
import uuid

import sqlalchemy as sa
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .db import get_engine

logger = logging.getLogger(__name__)

_SKIP = ("/core/health", "/docs", "/openapi.json", "/redoc")


def _skipped(path: str) -> bool:
    return path.startswith(_SKIP)


class LatencySimulationMiddleware(BaseHTTPMiddleware):
    """매 요청에 무작위 지연을 준다. 너무 빠른 가상 Core는 운영의 네트워크 특성을 가린다."""

    async def dispatch(self, request, call_next):
        lo, hi = settings.core_latency_ms_min, settings.core_latency_ms_max
        if hi > 0 and not _skipped(request.url.path):
            await asyncio.sleep(random.randint(lo, hi) / 1000)
        return await call_next(request)


class FailureSimulationMiddleware(BaseHTTPMiddleware):
    """정해진 확률로 503을 낸다. 의도된 실패임을 본문에 적어 실제 장애와 헷갈리지 않게 한다."""

    async def dispatch(self, request, call_next):
        rate = settings.core_fail_rate
        if rate > 0 and not _skipped(request.url.path) and random.random() < rate:
            logger.warning("의도된 실패를 냈다: %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=503,
                content={"error": "SIMULATED_FAILURE", "retry_after": 1},
            )
        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    """core_log에 호출 한 건을 남긴다. 본문은 남기지 않고 SHA-256 해시만 둔다.

    가장 바깥에 두기 때문에 시뮬레이션 503도 기록에 남고, 지연까지 포함한
    '호출자가 실제로 기다린 시간'이 duration_ms가 된다.
    """

    async def dispatch(self, request, call_next):
        if _skipped(request.url.path):
            return await call_next(request)

        started = time.time()

        # 본문은 해시만 남긴다. 회사·리포트 제목·해시가 로그에 그대로 쌓이면 그 자체가 유출 경로가 된다
        body = await request.body()
        params_hash = hashlib.sha256(body).hexdigest() if body else None

        # [주의] 미들웨어에서 body()를 읽으면 스트림이 소진돼 라우터가 본문을 못 받는다.
        # 읽은 값을 다시 흘려보내 줘야 POST가 멈추지 않는다
        async def _replay() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _replay

        response = await call_next(request)
        duration_ms = int((time.time() - started) * 1000)

        try:
            with get_engine().begin() as conn:
                conn.execute(sa.text("""
                    INSERT INTO core_log
                        (request_id, caller, caller_user_id, endpoint, method,
                         params_hash, status_code, duration_ms, error, created_at)
                    VALUES
                        (:request_id, :caller, :user_id, :endpoint, :method,
                         :params_hash, :status_code, :duration_ms, :error,
                         datetime('now'))
                """), {
                    "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
                    "caller": request.headers.get("X-Caller", "unknown"),
                    "user_id": request.headers.get("X-User-Id"),
                    "endpoint": request.url.path,
                    "method": request.method,
                    "params_hash": params_hash,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "error": None if response.status_code < 400 else str(response.status_code),
                })
        except Exception:
            # [주의] 감사 기록이 실패해도 호출 자체는 살린다. 다만 로그에는 남긴다
            logger.exception("core_log 기록 실패: %s", request.url.path)

        return response
