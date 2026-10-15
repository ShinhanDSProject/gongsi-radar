"""Core Service 진입점 — 리포트 발행 원장.

가상 원장이지만 프로세스를 따로 띄운다. 같은 코드 안에서 함수로 부르면 Core Zone 격리가
말로만 남는다. 별도 프로세스여야 네트워크 호출·인증 키·지연·실패가 전부 실제로 일어난다.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import check_keys, settings
from .db import init_db
from .middleware import (AuditMiddleware, FailureSimulationMiddleware,
                         LatencySimulationMiddleware)
from .publication_service import CoreConflict
from .routers import health, publications

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # [보안] 조회 키와 시스템 키가 같으면 여기서 멈춘다. 뜬 다음에 알아채면 이미 늦다
    check_keys()
    init_db()
    yield


app = FastAPI(title="Gongsi Core Service", version=settings.version, lifespan=lifespan)

# add_middleware는 나중에 넣은 것이 바깥이다.
# 감사를 가장 바깥에 둬야 시뮬레이션 503도 기록에 남는다
app.add_middleware(LatencySimulationMiddleware)
app.add_middleware(FailureSimulationMiddleware)
app.add_middleware(AuditMiddleware)


@app.exception_handler(CoreConflict)
async def _conflict_handler(_request: Request, exc: CoreConflict) -> JSONResponse:
    """409 본문은 CONTRACT §5대로 {"error": 코드, ...세부}.
    Quant-X 클라이언트처럼 body["detail"]["error"]를 읽는 쪽도 깨지지 않게 같은 내용을 detail에도 둔다.
    """
    body = {"error": exc.code, **exc.extra}
    return JSONResponse(status_code=409, content={**body, "detail": body})


app.include_router(health.router)
app.include_router(publications.router)
