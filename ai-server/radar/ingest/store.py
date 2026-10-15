"""적재 저장소. MariaDB(운영)와 SQLite(테스트·단독 실행) 양쪽에서 같은 코드가 돈다.

쓰기는 모두 upsert다. 같은 날 두 번 돌려도 결과가 같아야 하고(멱등), 수집 계정에는 DELETE 권한이 없다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import sqlalchemy as sa

from . import tables as T


def _insert(engine: sa.Engine, table: sa.Table):
    if engine.dialect.name in ("mysql", "mariadb"):
        from sqlalchemy.dialects.mysql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(table)


class IngestStore:
    def __init__(self, engine: sa.Engine):
        self.engine = engine

    # ---- upsert ----------------------------------------------------------------------------
    def upsert(self, table: sa.Table, rows: list[dict], keys: Iterable[str], update: Iterable[str]) -> int:
        """rows를 넣고 키가 겹치면 update 열만 갱신한다. 넣거나 고친 행 수(대략)를 돌려준다."""
        if not rows:
            return 0
        update = list(update)
        ins = _insert(self.engine, table)
        if self.engine.dialect.name in ("mysql", "mariadb"):
            stmt = ins.on_duplicate_key_update({c: ins.inserted[c] for c in update}) if update else ins.prefix_with("IGNORE")
        else:
            stmt = (ins.on_conflict_do_update(index_elements=list(keys), set_={c: ins.excluded[c] for c in update})
                    if update else ins.on_conflict_do_nothing(index_elements=list(keys)))
        with self.engine.begin() as conn:
            for k in range(0, len(rows), 500):
                conn.execute(stmt, rows[k:k + 500])
        return len(rows)

    def upsert_companies(self, rows: list[dict], today: date) -> int:
        """처음 본 회사는 first_seen=오늘. 이미 있는 회사는 이름·종목코드·last_seen만 갱신한다(first_seen 유지)."""
        payload = [{"corp_code": r["corp_code"], "corp_name": r["corp_name"], "stock_code": r.get("stock_code") or None,
                    "market": r.get("market"), "induty_code": r.get("induty_code"),
                    "induty_checked": today if r.get("induty_code") else None,
                    "listed": True, "first_seen": today, "last_seen": today} for r in rows]
        n = self.upsert(T.company, payload, ["corp_code"], ["corp_name", "stock_code", "listed", "last_seen"])
        # 목록 자체에 업종·시장이 있으면(샘플) 비어 있는 칸만 채운다
        with self.engine.begin() as conn:
            for r in payload:
                vals = {k: r[k] for k in ("market", "induty_code", "induty_checked") if r[k] is not None}
                if vals:
                    conn.execute(T.company.update().where(T.company.c.corp_code == r["corp_code"])
                                 .where(T.company.c.induty_code.is_(None) | T.company.c.market.is_(None)).values(**vals))
        return n

    def mark_delisted(self, seen: set[str], today: date) -> int:
        """오늘 목록에 없던 회사는 상장폐지 표시(행은 지우지 않는다 — 지난 공시·재무가 그 회사를 가리킨다)."""
        with self.engine.begin() as conn:
            listed = {r.corp_code for r in conn.execute(sa.select(T.company.c.corp_code).where(T.company.c.listed))}
            gone = listed - seen
            for code in gone:
                conn.execute(T.company.update().where(T.company.c.corp_code == code).values(listed=False))
        return len(gone)

    # ---- 조회 ------------------------------------------------------------------------------
    def count(self, table: sa.Table) -> int:
        with self.engine.connect() as conn:
            return conn.execute(sa.select(sa.func.count()).select_from(table)).scalar() or 0

    def has_data(self) -> bool:
        try:
            return self.count(T.company) > 0
        except sa.exc.SQLAlchemyError:        # 테이블이 없거나 권한이 없으면 적재 DB를 쓰지 않는다
            return False

    def latest_market_dates(self) -> dict[str, str]:
        with self.engine.connect() as conn:
            return {r.stock_code: r.d for r in conn.execute(
                sa.select(T.market_daily.c.stock_code, sa.func.max(T.market_daily.c.bas_dt).label("d"))
                .group_by(T.market_daily.c.stock_code))}

    def kill_switch(self) -> tuple[bool, str | None]:
        """Kill Switch 최신 상태. 테이블이 없으면 꺼진 것으로 본다(단독 실행)."""
        try:
            with self.engine.connect() as conn:
                row = conn.execute(sa.select(T.kill_switch_status.c.active, T.kill_switch_status.c.reason)
                                   .order_by(T.kill_switch_status.c.id.desc()).limit(1)).first()
        except sa.exc.SQLAlchemyError:
            return False, None
        return (bool(row.active), row.reason) if row else (False, None)

    # ---- 실행 기록 --------------------------------------------------------------------------
    def start_run(self, run_uid: str, mode: str, step: str, source: str) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(T.run.insert().values(run_uid=run_uid, mode=mode, step=step, status="RUNNING",
                                                     source=source, calls=0, rows_written=0, remaining=0,
                                                     started_at=datetime.now()))
            return res.inserted_primary_key[0]

    def finish_run(self, run_id: int, *, status: str, calls: int, rows: int, remaining: int = 0,
                   error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(T.run.update().where(T.run.c.id == run_id).values(
                status=status, calls=calls, rows_written=rows, remaining=remaining,
                error_message=(error or None) and error[:2000], finished_at=datetime.now()))

    def recent_runs(self, limit: int = 50) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(T.run).order_by(T.run.c.id.desc()).limit(limit)).mappings().all()
        return [dict(r) for r in rows]
