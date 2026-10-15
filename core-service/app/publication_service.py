"""발행 접수·승인 로직 (리포트 발행 원장).

접수 순서는 멱등성 → 일일 요청 한도 → 같은 리포트의 PENDING → 정정 대상 → 중복 발행이다.
비싼 검사를 뒤로 미루는 것도 있지만, 그보다 **거절 사유를 하나로 못박기 위해서**다.
여러 규칙에 동시에 걸리는 요청이 실행할 때마다 다른 이유로 거절되면 감사에서 설명하기 어렵다.

승인 순서는 상태(만료 포함) → 자기 승인 → 본문 해시 → 정정·중복 재확인이다.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.engine import Connection

from .config import settings
from .schemas import PublicationCreate, PublicationOut

# 상태 전이 규칙. PUBLISHED는 정정 승인으로만 SUPERSEDED가 되고, 나머지 종료 상태에서는 못 간다
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "PENDING": {"PUBLISHED", "REJECTED", "EXPIRED", "FAILED"},
    "PUBLISHED": {"SUPERSEDED"},
    "REJECTED": set(),
    "EXPIRED": set(),
    "FAILED": set(),
    "SUPERSEDED": set(),
}

# 하루 한도는 사용자가 사는 시간대(한국) 기준 자정으로 끊는다. 저장은 UTC로 한다
_KST = timezone(timedelta(hours=9))

_COLUMNS = """
    publication_id, report_id, corp_code, corp_name, period_label, title,
    content_hash, version, supersedes_id, status, submitted_by, decided_by,
    decided_at, published_at, reject_reason, created_at, decision_required_by
"""


class CoreConflict(Exception):
    """409 거절. 본문은 {"error": 코드, ...세부} 형태로 나간다(main.py 핸들러)."""

    def __init__(self, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra


def _iso(dt: datetime) -> str:
    # 자릿수를 고정해야 문자열 비교(만료·하루 한도)가 시간 순서와 일치한다
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


def _today_start_iso() -> str:
    """오늘(KST) 0시를 UTC 문자열로."""
    kst_now = datetime.now(_KST)
    return _iso(kst_now.replace(hour=0, minute=0, second=0, microsecond=0))


def _to_out(row: Any, *, duplicate: bool = False) -> PublicationOut:
    return PublicationOut(
        publicationId=row.publication_id, reportId=row.report_id,
        corpCode=row.corp_code, corpName=row.corp_name,
        periodLabel=row.period_label, title=row.title,
        contentHash=row.content_hash, version=row.version,
        supersedesId=row.supersedes_id, status=row.status,
        submittedBy=row.submitted_by, decidedBy=row.decided_by,
        decidedAt=row.decided_at, publishedAt=row.published_at,
        rejectReason=row.reject_reason, createdAt=row.created_at,
        decisionRequiredBy=row.decision_required_by, duplicate=duplicate,
    )


def _find(conn: Connection, publication_id: str) -> Any:
    return conn.execute(sa.text(
        f"SELECT {_COLUMNS} FROM publications WHERE publication_id = :pid"
    ), {"pid": publication_id}).first()


def _fetch(conn: Connection, publication_id: str) -> Any:
    row = _find(conn, publication_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"publication not found: {publication_id}")
    return row


def expire_stale(conn: Connection) -> int:
    """승인 시한을 넘긴 PENDING을 EXPIRED로 넘긴다.

    백그라운드 스케줄러 대신 조회·쓰기 직전에 한 번 돌린다. 프로세스가 꺼져 있는 동안에도
    시간은 흐르므로, 만료는 '언제 검사했는가'가 아니라 '시한을 넘겼는가'로 정해져야 한다.
    """
    res = conn.execute(sa.text("""
        UPDATE publications
           SET status = 'EXPIRED'
         WHERE status = 'PENDING' AND decision_required_by < :now
    """), {"now": now_iso()})
    return res.rowcount or 0


def _published_for(conn: Connection, corp_code: str, period_label: str) -> Any:
    return conn.execute(sa.text(f"""
        SELECT {_COLUMNS} FROM publications
         WHERE corp_code = :cc AND period_label = :pl AND status = 'PUBLISHED'
         ORDER BY version DESC LIMIT 1
    """), {"cc": corp_code, "pl": period_label}).first()


def _check_supersedes(conn: Connection, supersedes_id: str,
                      corp_code: str, period_label: str) -> None:
    """정정 대상은 지금 PUBLISHED이고 회사·기간이 같아야 한다."""
    target = _find(conn, supersedes_id)
    if target is None:
        raise CoreConflict("INVALID_SUPERSEDES", supersedesId=supersedes_id,
                           reason="NOT_FOUND")
    if target.status != "PUBLISHED":
        raise CoreConflict("INVALID_SUPERSEDES", supersedesId=supersedes_id,
                           reason="NOT_PUBLISHED", targetStatus=target.status)
    if target.corp_code != corp_code or target.period_label != period_label:
        raise CoreConflict("INVALID_SUPERSEDES", supersedesId=supersedes_id,
                           reason="CORP_OR_PERIOD_MISMATCH",
                           targetCorpCode=target.corp_code,
                           targetPeriodLabel=target.period_label)


def create_publication(conn: Connection, req: PublicationCreate,
                       idem_key: str) -> Tuple[PublicationOut, bool]:
    # ① 멱등성 — 같은 키가 있으면 새로 만들지 않고 있던 걸 그대로 돌려준다.
    #    Spring이 타임아웃 뒤 재시도해도 발행 요청이 두 건이 되지 않는다
    existing = conn.execute(sa.text(
        f"SELECT {_COLUMNS} FROM publications WHERE idempotency_key = :k"
    ), {"k": idem_key}).first()
    if existing is not None:
        return _to_out(existing, duplicate=True), True

    expire_stale(conn)

    # ② 일일 요청 한도 — 상태와 무관하게 '요청한 횟수'를 센다. 반려된 것도 요청은 요청이다
    daily = conn.execute(sa.text("""
        SELECT COUNT(*) FROM publications
         WHERE submitted_by = :uid AND created_at >= :since
    """), {"uid": req.submittedBy, "since": _today_start_iso()}).scalar_one()
    if daily >= settings.publication_daily_limit:
        raise CoreConflict("DAILY_LIMIT_EXCEEDED",
                           limit=settings.publication_daily_limit, alreadyUsed=daily)

    # ③ 같은 리포트에 결정 대기 중인 요청이 있으면 또 받지 않는다
    pending = conn.execute(sa.text("""
        SELECT publication_id FROM publications
         WHERE report_id = :rid AND status = 'PENDING'
    """), {"rid": req.reportId}).first()
    if pending is not None:
        raise CoreConflict("PENDING_EXISTS", reportId=req.reportId,
                           pendingPublicationId=pending.publication_id)

    # ④ 정정 발행이면 대상 검사, 아니면 ⑤ 이미 발행된 회사·기간인지 검사
    if req.supersedesId:
        _check_supersedes(conn, req.supersedesId, req.corpCode, req.periodLabel)
    else:
        published = _published_for(conn, req.corpCode, req.periodLabel)
        if published is not None:
            raise CoreConflict("DUPLICATE_PUBLICATION",
                               corpCode=req.corpCode, periodLabel=req.periodLabel,
                               publishedId=published.publication_id,
                               publishedVersion=published.version)

    # version = 같은 회사·기간에서 발행된 적 있는 건(PUBLISHED + 정정으로 밀려난 SUPERSEDED) + 1
    version = conn.execute(sa.text("""
        SELECT COUNT(*) FROM publications
         WHERE corp_code = :cc AND period_label = :pl
           AND status IN ('PUBLISHED', 'SUPERSEDED')
    """), {"cc": req.corpCode, "pl": req.periodLabel}).scalar_one() + 1

    created = datetime.now(timezone.utc)
    publication_id = str(uuid.uuid4())
    conn.execute(sa.text("""
        INSERT INTO publications
            (publication_id, idempotency_key, report_id, corp_code, corp_name,
             period_label, title, content_hash, version, supersedes_id, status,
             submitted_by, created_at, decision_required_by)
        VALUES
            (:pid, :idem, :rid, :cc, :cn, :pl, :title, :hash, :version, :sup,
             'PENDING', :by, :created_at, :required_by)
    """), {
        "pid": publication_id, "idem": idem_key, "rid": req.reportId,
        "cc": req.corpCode, "cn": req.corpName, "pl": req.periodLabel,
        "title": req.title, "hash": req.contentHash, "version": version,
        "sup": req.supersedesId, "by": req.submittedBy,
        "created_at": _iso(created),
        "required_by": _iso(created + timedelta(
            seconds=settings.publication_decision_timeout_sec)),
    })
    return _to_out(_fetch(conn, publication_id)), False


def _require_pending(row: Any) -> None:
    """만료는 INVALID_STATE와 구분해 EXPIRED로 알린다. 사람이 다시 요청해야 한다는 뜻이 다르다."""
    if row.status == "EXPIRED":
        raise CoreConflict("EXPIRED", publicationId=row.publication_id,
                           decisionRequiredBy=row.decision_required_by)
    if row.status != "PENDING":
        raise CoreConflict("INVALID_STATE", publicationId=row.publication_id,
                           currentStatus=row.status, requiredStatus="PENDING")


def _transition(current: str, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, set()):
        raise CoreConflict("INVALID_STATE", currentStatus=current, toStatus=new)


def approve(conn: Connection, publication_id: str, decided_by: str,
            content_hash: str) -> PublicationOut:
    expire_stale(conn)
    row = _fetch(conn, publication_id)
    _require_pending(row)

    # [보안] 자기 요청은 자기가 승인할 수 없다. Spring에서도 막지만 원장이 마지막으로 한 번 더 본다
    if decided_by == row.submitted_by:
        raise CoreConflict("SELF_APPROVAL", publicationId=publication_id,
                           submittedBy=row.submitted_by, decidedBy=decided_by)

    # 승인자가 본 본문과 요청된 본문이 같은지 해시로 대조한다
    if content_hash != row.content_hash:
        raise CoreConflict("CONTENT_CHANGED", publicationId=publication_id,
                           expected=row.content_hash, received=content_hash)

    # 요청 이후 사정이 바뀌었을 수 있다(같은 건에 정정이 두 건, 같은 회사·기간이 먼저 발행됨)
    if row.supersedes_id:
        _check_supersedes(conn, row.supersedes_id, row.corp_code, row.period_label)
    else:
        published = _published_for(conn, row.corp_code, row.period_label)
        if published is not None:
            raise CoreConflict("DUPLICATE_PUBLICATION",
                               corpCode=row.corp_code, periodLabel=row.period_label,
                               publishedId=published.publication_id,
                               publishedVersion=published.version)

    _transition(row.status, "PUBLISHED")
    now = now_iso()
    conn.execute(sa.text("""
        UPDATE publications
           SET status = 'PUBLISHED', decided_by = :by, decided_at = :now,
               published_at = :now
         WHERE publication_id = :pid
    """), {"by": decided_by, "now": now, "pid": publication_id})

    # 정정 발행이 승인되면 이전 건은 SUPERSEDED로 내린다. 같은 트랜잭션이라 둘 다 되거나 둘 다 안 된다
    if row.supersedes_id:
        _transition("PUBLISHED", "SUPERSEDED")
        conn.execute(sa.text("""
            UPDATE publications SET status = 'SUPERSEDED'
             WHERE publication_id = :sid AND status = 'PUBLISHED'
        """), {"sid": row.supersedes_id})

    return _to_out(_fetch(conn, publication_id))


def reject(conn: Connection, publication_id: str, decided_by: str,
           reason: Optional[str]) -> PublicationOut:
    expire_stale(conn)
    row = _fetch(conn, publication_id)
    _require_pending(row)
    _transition(row.status, "REJECTED")

    conn.execute(sa.text("""
        UPDATE publications
           SET status = 'REJECTED', decided_by = :by, decided_at = :now,
               reject_reason = :reason
         WHERE publication_id = :pid
    """), {"by": decided_by, "now": now_iso(), "reason": reason, "pid": publication_id})
    return _to_out(_fetch(conn, publication_id))


def get_publication(conn: Connection, publication_id: str) -> PublicationOut:
    expire_stale(conn)
    return _to_out(_fetch(conn, publication_id))


def list_publications(conn: Connection, corp_code: Optional[str],
                      pub_status: Optional[str], page: int = 0,
                      size: int = 20) -> Tuple[List[PublicationOut], int]:
    expire_stale(conn)

    where, params = [], {}
    if corp_code:
        where.append("corp_code = :cc")
        params["cc"] = corp_code
    if pub_status:
        where.append("status = :st")
        params["st"] = pub_status
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(sa.text(
        f"SELECT COUNT(*) FROM publications {clause}"), params).scalar_one()
    rows = conn.execute(sa.text(
        f"SELECT {_COLUMNS} FROM publications {clause} "
        f"ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), {**params, "limit": size, "offset": page * size}).all()

    return [_to_out(r) for r in rows], total
