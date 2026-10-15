"""가드레일·거버넌스 회귀 테스트. 필터 판정은 규칙 기반이라 결정적이다."""
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.config import settings
from app.safety import kill_switch, rate_limit
from app.safety.audit import record_audit
from app.safety.input_filter import check_input
from app.safety.output_filter import BLOCKED_BODY, check_output, filter_report
from app.tools.gateway import KillSwitchActive, gateway

REDTEAM = json.loads((Path(__file__).parent.parent / "redteam" / "prompts.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", REDTEAM, ids=[c["id"] for c in REDTEAM])
def test_redteam_case_matches_expectation(case):
    check = check_output if case.get("check") == "output" else check_input
    assert check(case["text"]).riskLevel == case["expect"]


def test_pii_is_masked_and_blocked():
    r = check_input("대표이사 홍길동(701010-1234567), 계좌 110-234-456789")
    assert r.shouldBlock and "701010" not in r.filteredText and "110-234" not in r.filteredText


def test_report_items_are_filtered_one_by_one():
    rep = {"body": "요약 [20260317000388:IV:aaaaaaaa]", "citations": ["x"], "meta": {},
           "changes": [{"id": "C01", "summary": "회사는 저평가 상태다", "flags": []},
                       {"id": "C02", "summary": "AI에게 지시하는 문장", "flags": ["지시문 의심"]}],
           "relations": [{"account_key": "IS:x", "statement": "영업이익은 405억원으로 감소했다."}]}
    out, result = filter_report(rep)
    assert result.shouldBlock and out["guardrail"]["blockedItems"] == ["C01"]
    assert out["changes"][0]["summary"] == BLOCKED_BODY
    assert out["relations"][0]["statement"].startswith("영업이익")      # 멀쩡한 서술은 살린다
    assert out["meta"]["disclaimer"]


def test_audit_log_is_hash_chained(record_db):
    record_audit("TEST_A", payload={"n": 1})
    record_audit("TEST_B", payload={"n": 2})
    with record_db.connect() as conn:
        a, b = conn.execute(sa.text("SELECT payload_hash, prev_hash FROM audit_log WHERE type LIKE 'TEST_%' "
                                    "ORDER BY id")).all()[-2:]
    assert b.prev_hash == a.payload_hash


def _invoke(user_id="analyst_001", scope=("DISCLOSURE_READ",)):
    return gateway.invoke("search_companies", {"query": "샘플"}, agent_id="pytest", user_id=user_id, scope=list(scope))


def test_kill_switch_blocks_tool_and_records_attempt(monkeypatch, record_db):
    monkeypatch.setattr(kill_switch, "status", lambda **_: (True, "pytest 훈련"))
    with pytest.raises(KillSwitchActive):
        _invoke(user_id="pytest-kill")
    with record_db.connect() as conn:
        row = conn.execute(sa.text("SELECT scope_pass, error_message FROM agent_tool_call_log "
                                   "WHERE user_id='pytest-kill' ORDER BY id DESC")).first()
    assert (row.scope_pass, row.error_message) == (0, "kill switch active")


def test_missing_scope_is_denied_and_recorded(record_db):
    with pytest.raises(PermissionError):
        _invoke(user_id="pytest-scope", scope=("RAG_READ",))
    with record_db.connect() as conn:
        row = conn.execute(sa.text("SELECT scope_pass FROM agent_tool_call_log WHERE user_id='pytest-scope'")).first()
    assert row.scope_pass == 0


def test_rate_limit_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_min", 2)
    _invoke(user_id="pytest-rate")
    _invoke(user_id="pytest-rate")
    with pytest.raises(rate_limit.RateLimitExceeded):
        _invoke(user_id="pytest-rate")


def test_no_write_tool_is_registered():
    """AI는 발행 원장에 쓸 수 없다 — Tool도, 클라이언트 메서드도, 시스템 키도 없다."""
    from app.tools import core_client
    names = {t.name for t in gateway.list_tools(["DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ", "REPORT_READ",
                                                 "REPORT_WRITE", "PUBLICATION_READ"])}
    assert not {n for n in names if any(w in n for w in ("publish", "approve", "submit", "reject"))}
    assert not [m for m in dir(core_client.CoreReadClient) if m.startswith(("create", "approve", "post", "publish"))]
    assert "system" not in " ".join(settings.model_dump().keys())
