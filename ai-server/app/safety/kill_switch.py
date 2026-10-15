"""Kill Switch. 상태는 Spring Boot가 DB(kill_switch_status)에 쓰고 여기서는 읽기만 한다.

정지 상태는 한 곳에만 있어야 한다. 두 서버가 각자 들면 "껐는데 왜 도나"가 된다.
[주의] 매 요청 DB 조회를 피하려고 TTL 3초 캐시를 둔다. 켜는 것이 즉시가 아니라는 뜻이고,
       비상 정지에서 이 몇 초를 받아들일 수 있는지가 설계 판단이다. /ai/health는 캐시를 거치지 않는다.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import sqlalchemy as sa

from ..config import settings
from ..tools.db import get_engine

logger = logging.getLogger(__name__)

_TTL_SEC = 3.0
_cache: Tuple[float, bool, Optional[str]] = (0.0, False, None)


def _read_db() -> Tuple[bool, Optional[str]]:
    """최신 한 줄이 현재 상태다. 토글할 때마다 행이 쌓인다(이력)."""
    with get_engine().connect() as conn:
        row = conn.execute(sa.text("SELECT active, reason FROM kill_switch_status ORDER BY id DESC LIMIT 1")).first()
    return (False, None) if row is None else (bool(row.active), row.reason)


def status(*, force_refresh: bool = False) -> Tuple[bool, Optional[str]]:
    """(활성 여부, 사유). env의 KILL_SWITCH_ENABLED와 OR — env는 DB로 끌 수 없는 마지막 수단이다."""
    global _cache
    if settings.kill_switch_enabled:
        return True, "환경변수 KILL_SWITCH_ENABLED"
    now = time.time()
    cached_at, active, reason = _cache
    if not force_refresh and now - cached_at < _TTL_SEC:
        return active, reason
    try:
        active, reason = _read_db()
    except Exception as e:
        # 상태를 못 읽었다고 서비스를 세우지 않는다. DB 장애가 곧 전면 중단이 되면 Kill Switch가 장애 원인이 된다
        logger.warning("kill_switch_status 조회 실패(%s). 직전 값을 유지한다", type(e).__name__)
        return active, reason
    _cache = (now, active, reason)
    return active, reason


def is_active(*, force_refresh: bool = False) -> bool:
    return status(force_refresh=force_refresh)[0]
