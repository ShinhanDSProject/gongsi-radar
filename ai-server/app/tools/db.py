"""MariaDB(gongsi) 애플리케이션 계정 엔진. 실행 이력·Kill Switch 조회·RAG 메타가 이 커넥션을 쓴다.
[보안] 최소 권한 계정(gongsi_app)이다. DELETE가 없고 감사 테이블은 읽기만 된다.
감사 기록은 이 엔진을 쓰지 않는다(safety/audit.py의 전용 엔진).
"""
from __future__ import annotations

from functools import lru_cache

import sqlalchemy as sa

from ..config import settings


@lru_cache(maxsize=1)
def get_engine() -> sa.Engine:
    return sa.create_engine(settings.mariadb_url, pool_pre_ping=True, pool_recycle=1800,
                            connect_args={"connect_timeout": 3})
