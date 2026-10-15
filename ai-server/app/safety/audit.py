"""감사 기록. audit_log · guardrail_event · agent_tool_call_log · llm_invocation_log에 쓴다.

원칙 세 가지(Quant-X 9장과 같다).
① 기록이 실패해도 본래 작업은 계속한다. 감사 실패로 서비스가 멈추면 감사가 장애 원인이 된다.
② 원문은 저장하지 않는다. 텍스트·Tool 인자는 SHA-256 해시로 남긴다.
③ 전용 커넥션으로만 쓴다. INSERT·SELECT만 가진 gongsi_audit 계정이라 이 경로로는 감사 로그를 고칠 수 없다.

공시레이더에서 더한 것: audit_log에 해시 체인(prev_hash)을 채운다. 같은 커넥션에서 직전 행의 payload_hash를
읽어 넣으므로, 중간 행을 지우거나 고치면 다음 행의 prev_hash와 어긋나 드러난다(삭제 권한이 없어도 이중 방어).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ..config import settings
from ..schemas.guardrail import GuardrailResult
from .context import get_execution_id, get_request_uid

logger = logging.getLogger(__name__)

_audit_engine: Optional[Engine] = None
_chain_lock = threading.Lock()


def get_audit_engine() -> Engine:
    """감사 기록 전용 엔진. tools/db.py의 앱 계정 엔진을 재사용하지 않는다 — 쓰는 경로와 고칠 수 있는 경로를 나눈다."""
    global _audit_engine
    if _audit_engine is None:
        _audit_engine = sa.create_engine(settings.mariadb_audit_url, pool_pre_ping=True,
                                         connect_args={"connect_timeout": 3})
    return _audit_engine


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def record_audit(type_: str, *, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                 request_id: Optional[int] = None, payload: Optional[Dict[str, Any]] = None) -> None:
    """audit_log 한 줄. payload에는 요약만 — 원문·PII는 넣지 않는다."""
    body = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    try:
        with _chain_lock, get_audit_engine().begin() as conn:
            prev = conn.execute(sa.text("SELECT payload_hash FROM audit_log ORDER BY id DESC LIMIT 1")).scalar()
            conn.execute(sa.text("""
                INSERT INTO audit_log (type, request_uid, user_id, agent_id, request_id, payload_json, payload_hash, prev_hash)
                VALUES (:type, :uid, :user_id, :agent_id, :request_id, :payload, :hash, :prev)
            """), {"type": type_, "uid": get_request_uid(), "user_id": user_id, "agent_id": agent_id,
                   "request_id": request_id, "payload": body, "hash": sha256(body), "prev": prev})
    except Exception as e:
        logger.error("audit_log 기록 실패: type=%s (%s: %s)", type_, type(e).__name__, e)


def record_guardrail(kind: str, result: GuardrailResult, original_text: str, *, user_id: Optional[str] = None,
                     agent_id: Optional[str] = None, request_id: Optional[int] = None) -> None:
    """guardrail_event 한 줄. kind는 INPUT · OUTPUT · CONTEXT(검색 문서 격리)."""
    try:
        with get_audit_engine().begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO guardrail_event (type, severity, request_uid, user_id, agent_id, request_id,
                                             detected_issues, payload_hash, filtered_text, blocked)
                VALUES (:type, :severity, :uid, :user_id, :agent_id, :request_id, :issues, :hash, :filtered, :blocked)
            """), {"type": kind, "severity": result.riskLevel, "uid": get_request_uid(), "user_id": user_id,
                   "agent_id": agent_id, "request_id": request_id,
                   "issues": json.dumps(result.detectedIssues, ensure_ascii=False),
                   "hash": sha256(original_text), "filtered": (result.filteredText or "")[:60000],
                   "blocked": result.shouldBlock})
    except Exception as e:
        logger.error("guardrail_event 기록 실패: type=%s (%s: %s)", kind, type(e).__name__, e)
    if result.shouldBlock:
        record_audit("GUARDRAIL_BLOCKED", user_id=user_id, agent_id=agent_id, request_id=request_id,
                     payload={"kind": kind, "issues": result.detectedIssues})


def record_tool_call(*, tool_name: str, agent_id: str, user_id: str, scope: List[str], scope_pass: bool,
                     params: Dict[str, Any], result_summary: str, duration_ms: int, error: Optional[str]) -> None:
    """agent_tool_call_log 한 줄. execution_id는 contextvar — 직접 호출이면 NULL."""
    try:
        with get_audit_engine().begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO agent_tool_call_log (request_uid, execution_id, agent_id, user_id, tool_name, scope_json,
                                                 scope_pass, params_hash, result_summary, duration_ms, error_message)
                VALUES (:uid, :execution_id, :agent_id, :user_id, :tool_name, :scope, :scope_pass, :params_hash,
                        :summary, :duration_ms, :error)
            """), {"uid": get_request_uid(), "execution_id": get_execution_id(), "agent_id": agent_id,
                   "user_id": user_id, "tool_name": tool_name, "scope": json.dumps(scope, ensure_ascii=False),
                   "scope_pass": scope_pass,
                   "params_hash": sha256(json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)),
                   "summary": (result_summary or "")[:60000], "duration_ms": duration_ms, "error": error})
    except Exception as e:
        logger.error("agent_tool_call_log 기록 실패: tool=%s (%s: %s)", tool_name, type(e).__name__, e)


def record_llm_invocation(*, provider: str, model_name: str, agent_id: str, prompt_hash: str, prompt_chars: int,
                          prompt_tokens: Optional[int], completion_tokens: Optional[int], duration_ms: int,
                          error: Optional[str]) -> None:
    """llm_invocation_log 한 줄. 프롬프트 전문은 넣지 않는다(호출한 쪽이 해시로 넘긴다)."""
    try:
        with get_audit_engine().begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO llm_invocation_log (request_uid, execution_id, agent_id, provider, model_name, prompt_hash,
                                                prompt_chars, prompt_tokens, completion_tokens, duration_ms, status,
                                                error_message)
                VALUES (:uid, :execution_id, :agent_id, :provider, :model_name, :prompt_hash, :prompt_chars,
                        :prompt_tokens, :completion_tokens, :duration_ms, :status, :error)
            """), {"uid": get_request_uid(), "execution_id": get_execution_id(), "agent_id": agent_id,
                   "provider": provider, "model_name": model_name, "prompt_hash": prompt_hash,
                   "prompt_chars": prompt_chars, "prompt_tokens": prompt_tokens,
                   "completion_tokens": completion_tokens, "duration_ms": duration_ms,
                   "status": "FAIL" if error else "SUCCESS", "error": error})
    except Exception as e:
        logger.error("llm_invocation_log 기록 실패: model=%s (%s: %s)", model_name, type(e).__name__, e)
