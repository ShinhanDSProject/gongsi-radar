"""AI 서버(app/) 테스트 공통 설정.

감사 테이블은 append-only라 테스트가 쓴 행을 지울 수 없다. 그래서 기록 경로(감사 엔진·실행 이력·RAG 메타)를
인메모리 SQLite로 돌린다. Kill Switch는 기본 꺼짐으로 고정하고, 켜는 테스트만 따로 바꾼다.
LLM은 mock, 임베딩은 hash, Chroma는 임시 폴더 — 외부 서비스 없이 전 구간이 돈다.
radar 라이브러리 테스트(unittest)는 이 설정과 무관하게 그대로 돈다.

데이터 소스는 샘플(저장소 루트 samples/data)로 고정한다. 앱 기본값은 RADAR_SOURCE=service(Spring 내부 데이터 API)라
그대로 두면 Spring이 떠 있어야 테스트가 돈다. app을 import하기 전에(.env·기본값보다 먼저) 심는다.
"""
import os
import tempfile

os.environ["RADAR_SOURCE"] = "sample"

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.graph import execution_store
from app.rag import indexer
from app.safety import audit, kill_switch, rate_limit

_DDL = [
    """CREATE TABLE agent_execution (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL,
        job_id TEXT NOT NULL, agent_id TEXT NOT NULL, step_order INTEGER NOT NULL, status TEXT NOT NULL,
        input_text TEXT, output_text TEXT, model_provider TEXT, model_name TEXT, duration_ms INTEGER,
        error_message TEXT, started_at TEXT, finished_at TEXT)""",
    """CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, request_uid TEXT,
        user_id TEXT, agent_id TEXT, request_id INTEGER, payload_json TEXT NOT NULL, payload_hash TEXT, prev_hash TEXT)""",
    """CREATE TABLE guardrail_event (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, severity TEXT NOT NULL,
        request_uid TEXT, user_id TEXT, agent_id TEXT, request_id INTEGER, detected_issues TEXT NOT NULL,
        payload_hash TEXT NOT NULL, filtered_text TEXT, blocked INTEGER NOT NULL)""",
    """CREATE TABLE agent_tool_call_log (id INTEGER PRIMARY KEY AUTOINCREMENT, request_uid TEXT, execution_id INTEGER,
        agent_id TEXT NOT NULL, user_id TEXT NOT NULL, tool_name TEXT NOT NULL, scope_json TEXT NOT NULL,
        scope_pass INTEGER NOT NULL, params_hash TEXT, result_summary TEXT, duration_ms INTEGER, error_message TEXT)""",
    """CREATE TABLE llm_invocation_log (id INTEGER PRIMARY KEY AUTOINCREMENT, request_uid TEXT, execution_id INTEGER,
        agent_id TEXT, provider TEXT NOT NULL, model_name TEXT NOT NULL, prompt_hash TEXT, prompt_chars INTEGER,
        prompt_tokens INTEGER, completion_tokens INTEGER, duration_ms INTEGER, status TEXT NOT NULL, error_message TEXT)""",
]


@pytest.fixture(scope="session", autouse=True)
def record_db():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        for ddl in _DDL:
            conn.execute(sa.text(ddl))
    mp = pytest.MonkeyPatch()
    mp.setattr(audit, "get_audit_engine", lambda: engine)
    mp.setattr(execution_store, "get_engine", lambda: engine)
    mp.setattr(indexer, "get_engine", lambda: engine)        # RAG 메타 테이블이 없어 경고만 남고 색인은 된다
    mp.setattr(settings, "llm_provider", "mock")
    mp.setattr(settings, "embedding_provider", "hash")
    mp.setattr(settings, "chroma_persist_dir", tempfile.mkdtemp(prefix="gongsi-chroma-"))
    mp.setattr(settings, "rate_limit_per_min", 0)
    yield engine
    mp.undo()
    engine.dispose()


@pytest.fixture(autouse=True)
def kill_switch_off(monkeypatch):
    monkeypatch.setattr(kill_switch, "status", lambda **_: (False, None))
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture(scope="session", autouse=True)
def registered():
    from app.tools.registry import register_default_tools
    register_default_tools()
