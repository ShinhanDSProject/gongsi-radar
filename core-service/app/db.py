"""SQLite 엔진 단일 진입점.
Core Zone은 Middle Zone의 MariaDB와 파일부터 분리한다. 실제 발행 시스템으로 갈아끼울 때
이쪽 DB를 통째로 버릴 수 있어야 하기 때문.
"""
from __future__ import annotations
import logging
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import settings

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        db_path = Path(settings.core_db_path)
        if not db_path.is_absolute():
            db_path = _BASE_DIR / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = sa.create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _apply_pragma)
    return _engine


def _apply_pragma(dbapi_conn, _record) -> None:
    """[주의] SQLite 기본 모드는 쓰기 중에 읽기를 막는다.
    승인과 조회가 겹치면 'database is locked'가 나므로 WAL로 바꾸고 대기 시간을 준다.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=3000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def _run_script(filename: str) -> None:
    sql = (_BASE_DIR / filename).read_text(encoding="utf-8")
    raw = get_engine().raw_connection()
    try:
        raw.cursor().executescript(sql)
        raw.commit()
    finally:
        raw.close()


def init_db() -> None:
    """스키마 생성. 발행 원장은 비어서 시작하므로 시드는 없다."""
    _run_script("schema.sql")
    with get_engine().connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM publications")).scalar_one()
    logger.info("발행 원장 %d건으로 시작한다", count)
