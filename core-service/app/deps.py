"""인증 의존성. Read와 Write가 서로 다른 키를 본다.

[보안] 이 파일이 Core Zone의 핵심이다. AI 서버는 Read 키만 갖고 있으므로
발행·승인 엔드포인트에 아무리 요청을 보내도 403에서 끝난다.
"""
import hmac

from fastapi import Header, HTTPException, status

from .config import settings


def _same(given: str, expected: str) -> bool:
    # 키 비교는 시간 차로 새지 않게 상수 시간 비교를 쓴다
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def require_internal_key(x_internal_api_key: str = Header(default="")) -> None:
    """Tool Gateway(AI 서버)가 발행 원장을 조회할 때 쓰는 키."""
    if not _same(x_internal_api_key, settings.core_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or missing X-Internal-API-Key",
        )


def require_system_key(x_system_key: str = Header(default="")) -> None:
    """Spring Boot가 사람의 승인을 받고 Write를 부를 때 쓰는 키.
    Read 키로는 통과할 수 없다. 두 값이 같으면 서비스가 뜨지 않는다(config.check_keys).
    """
    if not _same(x_system_key, settings.core_system_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or missing X-System-Key",
        )
