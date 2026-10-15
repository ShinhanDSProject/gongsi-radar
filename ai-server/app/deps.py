"""라우터 공통 의존성. 이 서버는 내부 키를 가진 호출자(Spring Boot)만 믿는다."""
from typing import List

from fastapi import Header, HTTPException, status

from .config import settings


async def verify_internal_key(x_internal_api_key: str = Header(...)) -> None:
    if x_internal_api_key != settings.ai_server_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")


async def require_user_id(x_user_id: str = Header(...)) -> str:
    return x_user_id


def parse_scopes(header_value: str) -> List[str]:
    """`X-User-Scopes: A,B` → ["A", "B"]. Scope는 Spring이 JWT에서 꺼내 넣는다."""
    return [s.strip() for s in (header_value or "").split(",") if s.strip()]
