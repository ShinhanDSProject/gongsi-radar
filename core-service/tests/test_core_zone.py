"""Core Zone(리포트 발행 원장) "막히는 것들" 회귀 테스트.
임시 SQLite 파일로 서비스를 띄워 인증 분리·멱등성·거절 사유·상태 전이·만료·정정 발행을 확인한다.
"""
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

_DB = os.path.join(tempfile.mkdtemp(), "core-test.db")
os.environ["CORE_DB_PATH"] = _DB
os.environ["CORE_FAIL_RATE"] = "0"
os.environ["CORE_LATENCY_MS_MAX"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.config import check_keys, settings
from app.main import app

READ = {"X-Internal-API-Key": settings.core_api_key}
SYSTEM = {"X-System-Key": settings.core_system_key}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _corp() -> str:
    # 테스트끼리 회사·기간이 겹치지 않게 매번 새 고유번호를 쓴다
    return uuid.uuid4().hex[:8]


def _submit(client, *, corp=None, period="2025 사업보고서", report_id=None, content="본문 v1",
            submitted_by=None, supersedes=None, key=None, headers=SYSTEM):
    return client.post("/core/publications", json={
        "reportId": report_id if report_id is not None else uuid.uuid4().int % 1_000_000,
        "corpCode": corp or _corp(), "corpName": "샘플소재㈜", "periodLabel": period,
        "title": "샘플소재㈜ 2025 사업보고서 전년 대비 비교", "contentHash": _hash(content),
        # 요청자를 매번 바꾼다. 하루 한도(20건)가 다른 테스트를 막지 않게
        "submittedBy": submitted_by or f"analyst_{uuid.uuid4().hex[:6]}", "supersedesId": supersedes,
    }, headers={**headers, "X-Idempotency-Key": key or str(uuid.uuid4())})


def _approve(client, pid, *, by="senior_001", content="본문 v1", headers=SYSTEM):
    return client.post(f"/core/publications/{pid}/approve",
                       json={"decidedBy": by, "contentHash": _hash(content)}, headers=headers)


def _error(resp) -> str:
    assert resp.status_code == 409, resp.text
    return resp.json()["error"]


# ───── 인증 분리 ─────

def test_health_needs_no_key(client):
    body = client.get("/core/health").json()
    assert body["service"] == "gongsi-core-service"
    assert body["fail_rate"] == 0


def test_read_key_cannot_write(client):
    assert client.get("/core/publications", headers=READ).status_code == 200
    assert client.get("/core/publications").status_code == 403                    # 키 없음
    assert client.get("/core/publications", headers=SYSTEM).status_code == 403     # 시스템 키로 조회도 안 된다
    assert _submit(client, headers=READ).status_code == 403                         # 조회 키로 발행 요청
    pid = _submit(client).json()["publicationId"]
    assert _approve(client, pid, headers=READ).status_code == 403                   # 조회 키로 승인
    assert client.post(f"/core/publications/{pid}/reject", json={"decidedBy": "senior_001"},
                       headers=READ).status_code == 403


def test_equal_keys_refuse_to_start(monkeypatch):
    monkeypatch.setattr(settings, "core_system_key", settings.core_api_key)
    with pytest.raises(RuntimeError):
        check_keys()


# ───── 멱등성 ─────

def test_same_idempotency_key_returns_existing(client):
    key = str(uuid.uuid4())
    first = _submit(client, key=key)
    second = _submit(client, key=key)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["duplicate"] is True
    assert first.json()["publicationId"] == second.json()["publicationId"]
    assert first.json()["status"] == "PENDING" and first.json()["version"] == 1


def test_missing_idempotency_key_is_rejected(client):
    resp = client.post("/core/publications", json={}, headers=SYSTEM)
    assert resp.status_code == 422


# ───── 접수 거절 사유 ─────

def test_duplicate_publication(client):
    corp = _corp()
    pid = _submit(client, corp=corp).json()["publicationId"]
    assert _approve(client, pid).json()["status"] == "PUBLISHED"
    resp = _submit(client, corp=corp)                       # 같은 회사·기간, supersedesId 없음
    assert _error(resp) == "DUPLICATE_PUBLICATION"
    assert resp.json()["publishedId"] == pid


def test_pending_exists(client):
    _submit(client, report_id=424242)
    assert _error(_submit(client, report_id=424242)) == "PENDING_EXISTS"


def test_daily_limit_exceeded(client, monkeypatch):
    monkeypatch.setattr(settings, "publication_daily_limit", 2)
    who = f"analyst_{uuid.uuid4().hex[:6]}"
    assert _submit(client, submitted_by=who).status_code == 201
    assert _submit(client, submitted_by=who).status_code == 201
    resp = _submit(client, submitted_by=who)
    assert _error(resp) == "DAILY_LIMIT_EXCEEDED"
    assert resp.json()["limit"] == 2


@pytest.mark.parametrize("case", ["not_found", "not_published", "other_period"])
def test_invalid_supersedes(client, case):
    corp = _corp()
    if case == "not_found":
        target = str(uuid.uuid4())
    elif case == "not_published":
        target = _submit(client, corp=corp).json()["publicationId"]          # 아직 PENDING
    else:
        target = _submit(client, corp=corp).json()["publicationId"]
        _approve(client, target)
    period = "2024 사업보고서" if case == "other_period" else "2025 사업보고서"
    resp = _submit(client, corp=corp, period=period, supersedes=target)
    assert _error(resp) == "INVALID_SUPERSEDES"


# ───── 승인 거절 사유·상태 머신 ─────

def test_self_approval_forbidden(client):
    pid = _submit(client, submitted_by="senior_001").json()["publicationId"]
    assert _error(_approve(client, pid, by="senior_001")) == "SELF_APPROVAL"


def test_content_changed(client):
    pid = _submit(client, content="본문 v1").json()["publicationId"]
    resp = _approve(client, pid, content="몰래 고친 본문")
    assert _error(resp) == "CONTENT_CHANGED"
    assert resp.json()["detail"]["error"] == "CONTENT_CHANGED"       # Quant-X 형식 호환
    # 거절된 뒤에도 PENDING 그대로 남는다
    assert client.get(f"/core/publications/{pid}", headers=READ).json()["status"] == "PENDING"


def test_published_cannot_be_approved_twice(client):
    pid = _submit(client).json()["publicationId"]
    body = _approve(client, pid).json()
    assert body["status"] == "PUBLISHED"
    assert body["decidedBy"] == "senior_001" and body["publishedAt"]
    resp = _approve(client, pid)
    assert _error(resp) == "INVALID_STATE"
    assert resp.json()["currentStatus"] == "PUBLISHED"


def test_reject_then_cannot_approve(client):
    pid = _submit(client).json()["publicationId"]
    resp = client.post(f"/core/publications/{pid}/reject",
                       json={"decidedBy": "senior_001", "reason": "근거 문단 부족"}, headers=SYSTEM)
    assert resp.json()["status"] == "REJECTED"
    assert resp.json()["rejectReason"] == "근거 문단 부족"
    assert _error(_approve(client, pid)) == "INVALID_STATE"


def test_expired_lazily_on_read_and_write(client, monkeypatch):
    monkeypatch.setattr(settings, "publication_decision_timeout_sec", -1)   # 접수 즉시 시한 초과
    pid = _submit(client).json()["publicationId"]
    # 조회 시점에 만료가 적용된다
    assert client.get(f"/core/publications/{pid}", headers=READ).json()["status"] == "EXPIRED"
    assert _error(_approve(client, pid)) == "EXPIRED"
    resp = client.post(f"/core/publications/{pid}/reject", json={"decidedBy": "senior_001"}, headers=SYSTEM)
    assert _error(resp) == "EXPIRED"


def test_expired_frees_report_for_resubmit(client, monkeypatch):
    monkeypatch.setattr(settings, "publication_decision_timeout_sec", -1)
    _submit(client, report_id=777001)
    monkeypatch.setattr(settings, "publication_decision_timeout_sec", 86400)
    # 쓰기 시점에도 만료가 먼저 적용되므로 PENDING_EXISTS가 아니다
    assert _submit(client, report_id=777001).status_code == 201


# ───── 정정 발행 ─────

def test_supersede_flow(client):
    corp = _corp()
    v1 = _submit(client, corp=corp, content="v1").json()
    _approve(client, v1["publicationId"], content="v1")

    v2 = _submit(client, corp=corp, content="v2", supersedes=v1["publicationId"]).json()
    assert v2["version"] == 2 and v2["supersedesId"] == v1["publicationId"]
    # 승인 전까지 v1은 PUBLISHED 그대로
    assert client.get(f"/core/publications/{v1['publicationId']}", headers=READ).json()["status"] == "PUBLISHED"

    assert _approve(client, v2["publicationId"], content="v2").json()["status"] == "PUBLISHED"
    assert client.get(f"/core/publications/{v1['publicationId']}", headers=READ).json()["status"] == "SUPERSEDED"

    # 밀려난 v1을 다시 정정할 수는 없다. 최신 v2를 정정하면 version 3
    assert _error(_submit(client, corp=corp, supersedes=v1["publicationId"])) == "INVALID_SUPERSEDES"
    v3 = _submit(client, corp=corp, content="v3", supersedes=v2["publicationId"]).json()
    assert v3["version"] == 3


def test_two_corrections_only_first_wins(client):
    corp = _corp()
    v1 = _submit(client, corp=corp).json()["publicationId"]
    _approve(client, v1)
    a = _submit(client, corp=corp, content="a", supersedes=v1).json()["publicationId"]
    b = _submit(client, corp=corp, content="b", supersedes=v1).json()["publicationId"]
    assert _approve(client, a, content="a").status_code == 200
    assert _error(_approve(client, b, content="b")) == "INVALID_SUPERSEDES"


# ───── 조회 ─────

def test_list_filters_and_paging(client):
    corp = _corp()
    for _ in range(3):
        _submit(client, corp=corp)
    body = client.get("/core/publications", params={"corp_code": corp, "status": "PENDING", "size": 2},
                      headers=READ).json()
    assert body["total"] == 3 and len(body["items"]) == 2
    page2 = client.get("/core/publications", params={"corp_code": corp, "page": 1, "size": 2},
                       headers=READ).json()
    assert len(page2["items"]) == 1
    assert client.get("/core/publications/no-such-id", headers=READ).status_code == 404


# ───── 감사 로그 ─────

def test_core_log_has_hash_not_body(client):
    marker = f"민감-제목-{uuid.uuid4().hex}"
    payload = {"reportId": 99, "corpCode": _corp(), "corpName": marker, "periodLabel": "2025 사업보고서",
               "title": marker, "contentHash": _hash("x"), "submittedBy": "analyst_002"}
    raw = json.dumps(payload).encode()
    client.post("/core/publications", content=raw,
                headers={**SYSTEM, "X-Idempotency-Key": str(uuid.uuid4()),
                         "Content-Type": "application/json", "X-Caller": "spring-boot"})

    con = sqlite3.connect(_DB)
    try:
        rows = con.execute("SELECT * FROM core_log").fetchall()
        last = con.execute("SELECT caller, params_hash, status_code FROM core_log "
                           "WHERE caller = 'spring-boot' ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        con.close()
    assert not any(marker in str(col) for row in rows for col in row)
    assert last == ("spring-boot", hashlib.sha256(raw).hexdigest(), 201)
