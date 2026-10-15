"""AI 서버 진입점(Middle Zone · AI Layer). Spring Boot만 내부 키로 부른다.

logging.basicConfig를 여기서 부른다. 없으면 우리 모듈의 logger.info 감사 줄이 통째로 버려진다(uvicorn은 자기 로거만 설정한다).
로그 패턴에 request_uid를 넣어 감사 테이블과 로그를 같은 값으로 오갈 수 있게 한다.
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()            # radar 라이브러리가 읽는 RADAR_* 환경변수도 .env에서 채운다

from fastapi import FastAPI  # noqa: E402

from .config import settings  # noqa: E402
from .routers import agents, analyses, companies, guardrails, health, llm, market, rag, tools  # noqa: E402
from .safety.context import RequestUidLogFilter  # noqa: E402
from .tools.registry import register_default_tools  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(request_uid)s] %(name)s: %(message)s")
# 필터는 로거가 아니라 핸들러에 건다. 하위 로거에서 올라온 레코드도 속성이 채워지게
for _h in logging.getLogger().handlers:
    _h.addFilter(RequestUidLogFilter())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    register_default_tools()
    yield


app = FastAPI(title=settings.service_name, version=settings.version, lifespan=lifespan)
for r in (health, analyses, rag, tools, agents, guardrails, llm, companies, market):
    app.include_router(r.router)


@app.get("/")
def root() -> dict:
    return {"service": settings.service_name, "version": settings.version}
