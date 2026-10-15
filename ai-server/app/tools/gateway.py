"""Tool Gateway — 모든 데이터 접근의 단일 관문.
- Kill Switch · Rate Limit · Scope 검사(이 순서를 고정한다: 넓은 통제부터 좁은 통제로)
- 호출 기록(인메모리 창 + agent_tool_call_log)

[통제] 순서를 고정하는 이유: 세 통제에 동시에 걸리는 호출이 실행할 때마다 다른 사유로 거절되면
       감사에서 설명할 수 없다.
[보안] 발행·승인 Tool은 등록하지 않는다. 프롬프트로 "쓰지 마라"고 부탁하는 것과 코드에 없어서 못 부르는 것은 다르다.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..config import settings
from ..safety import kill_switch, rate_limit
from ..safety.audit import record_tool_call
from ..safety.context import set_caller_user_id

logger = logging.getLogger(__name__)


class KillSwitchActive(Exception):
    """Kill Switch가 켜져 있어 Tool을 부를 수 없다. 라우터가 503으로 바꾼다."""


@dataclass
class ToolSpec:
    name: str
    func: Callable[..., Any]
    required_scopes: List[str]
    description: str = ""
    summarize: Optional[Callable[[Any], str]] = None    # 기록용 요약(없으면 문자열 앞부분)


@dataclass
class ToolCallRecord:
    record_id: str
    tool_name: str
    agent_id: str
    user_id: str
    scope_pass: bool
    duration_ms: int
    error: Optional[str] = None
    summary: str = ""
    timestamp: float = field(default_factory=time.time)


class ToolGateway:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._call_log: List[ToolCallRecord] = []
        self._lock = threading.Lock()

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self, scope: List[str]) -> List[ToolSpec]:
        return [s for s in self._tools.values() if all(r in scope for r in s.required_scopes)]

    def invoke(self, tool_name: str, params: Dict[str, Any], *, agent_id: str, user_id: str,
               scope: List[str]) -> Any:
        spec = self._tools.get(tool_name)
        if spec is None:
            raise KeyError(f"Tool not found: {tool_name}")

        def deny(reason: str) -> None:
            self._record(ToolCallRecord(str(uuid.uuid4()), tool_name, agent_id, user_id, False, 0, error=reason),
                         params=params, scope=scope)

        # ① Kill Switch — 창구 하나를 닫는 것이 비상 정지의 뜻에 맞는다(Core Zone 조회까지 함께 멈춘다)
        active, reason = kill_switch.status()
        if active:
            deny("kill switch active")
            raise KillSwitchActive(reason or "Kill Switch is active")
        # ② Rate Limit — 인젝션에 걸린 Agent가 같은 호출을 반복하는 것을 잡는다
        try:
            rate_limit.check(user_id, settings.rate_limit_per_min)
        except rate_limit.RateLimitExceeded as e:
            deny(str(e))
            raise
        # ③ Scope — 거부된 시도도 감사 대상이다
        missing = [r for r in spec.required_scopes if r not in scope]
        if missing:
            deny(f"missing scope: {missing}")
            raise PermissionError(f"missing scope: {missing}")

        # ④ 호출. 호출자를 컨텍스트에 심어 Core Zone 조회 기록이 같은 사람으로 남게 한다
        set_caller_user_id(user_id)
        start = time.time()
        error: Optional[str] = None
        result: Any = None
        try:
            result = spec.func(**params)
            return result
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.warning("tool failed: %s (%s)", tool_name, error)
            raise
        finally:
            summary = ""
            if result is not None:
                summary = spec.summarize(result) if spec.summarize else _summarize(result)
            self._record(ToolCallRecord(str(uuid.uuid4()), tool_name, agent_id, user_id, True,
                                        int((time.time() - start) * 1000), error=error, summary=summary),
                         params=params, scope=scope)

    def _record(self, record: ToolCallRecord, *, params: Dict[str, Any], scope: List[str]) -> None:
        """인메모리 창은 DB가 죽어도 최근 호출을 보기 위한 것이다. 정본은 DB다."""
        with self._lock:
            self._call_log.append(record)
            del self._call_log[:-500]
        logger.info("tool_call %s | agent=%s | scope_pass=%s | %dms | err=%s", record.tool_name, record.agent_id,
                    record.scope_pass, record.duration_ms, record.error)
        record_tool_call(tool_name=record.tool_name, agent_id=record.agent_id, user_id=record.user_id,
                         scope=scope, scope_pass=record.scope_pass, params=params,
                         result_summary=record.summary, duration_ms=record.duration_ms, error=record.error)

    def recent_calls(self, limit: int = 50) -> List[ToolCallRecord]:
        return self._call_log[-limit:]


def _summarize(value: Any, max_len: int = 200) -> str:
    s = str(value)
    return s if len(s) <= max_len else s[:max_len] + "..."


gateway = ToolGateway()
