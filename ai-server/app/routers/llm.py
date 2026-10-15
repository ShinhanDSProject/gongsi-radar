"""LLM provider 조회·전환.

전환 실행은 AI 서버가 하는데 권한 검증은 왜 Spring에 있는가.
"누가 Senior인가"는 Service Layer의 지식이다. AI 서버는 내부 키를 가진
호출자(=Spring Boot)만 믿고, 사람의 권한은 Spring이 JWT로 가린다.
Kill Switch를 Spring에 둔 것과 같은 구도다 — 판단 주체를 바꿀 대상 바깥에 둔다.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..deps import verify_internal_key
from ..llm import factory
from ..safety.context import set_request_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/llm", tags=["llm"])


class SwitchRequest(BaseModel):
    provider: str


@router.get("/providers", dependencies=[Depends(verify_internal_key)])
def providers() -> dict:
    return factory.list_providers()


@router.post("/switch", dependencies=[Depends(verify_internal_key)])
def switch(req: SwitchRequest,
           x_request_id: str = Header(default="")) -> dict:
    set_request_uid(x_request_id or None)
    try:
        factory.switch_provider(req.provider)
    except ValueError as e:                    # 없는 provider — 요청이 틀렸다
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:                  # 폐쇄망 차단 — 요청은 맞지만 정책이 막는다
        raise HTTPException(status_code=403, detail=str(e))
    # 전환 후 현황을 그대로 돌려준다. 화면이 한 번의 왕복으로 최신 상태가 된다
    return factory.list_providers()
