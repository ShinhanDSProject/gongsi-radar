"""요청 하나를 관통하는 값들. 인자로 넘기지 않고 contextvars로 들고 다닌다.

[감사] request_uid는 Spring Boot가 만들어 X-Request-ID 헤더로 넘긴다. Tool Gateway·가드레일·Core Zone 조회가
       모두 같은 값을 기록해야 "이 조회는 누가 왜 했는가"에 답할 수 있다.
       인자로 넘기지 않는 이유: Tool 함수 시그니처에 끼우면 LLM이 채우는 인자 스키마에도 새어 들어간다.

job_id는 공시레이더에서 더한 값이다. 분석 1건의 Worker들이 같은 파싱 결과(radar 세션)를 나눠 쓰도록
Tool이 "지금 어느 분석 안에서 불렸는가"를 알아야 하는데, 이것도 LLM이 지어내면 안 되는 값이다.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

_request_uid: ContextVar[Optional[str]] = ContextVar("request_uid", default=None)
_execution_id: ContextVar[Optional[int]] = ContextVar("execution_id", default=None)
_caller_user_id: ContextVar[Optional[str]] = ContextVar("caller_user_id", default=None)
_job_id: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


def set_request_uid(value: Optional[str]) -> str:
    """헤더로 받은 값을 심는다. 없으면 여기서 만든다(FastAPI를 직접 부른 경우)."""
    uid = value or f"req-{uuid.uuid4()}"
    _request_uid.set(uid)
    return uid


def get_request_uid() -> Optional[str]:
    return _request_uid.get()


def set_execution_id(value: Optional[int]) -> None:
    """Worker 실행이 시작될 때 agent_execution.id를 심는다."""
    _execution_id.set(value)


def get_execution_id() -> Optional[int]:
    return _execution_id.get()


def set_caller_user_id(value: Optional[str]) -> None:
    """Tool Gateway가 호출 직전에 심는다. Core Zone 조회 기록의 호출자가 된다."""
    _caller_user_id.set(value)


def get_caller_user_id() -> Optional[str]:
    return _caller_user_id.get()


def set_job_id(value: Optional[str]) -> None:
    _job_id.set(value)


def get_job_id() -> Optional[str]:
    return _job_id.get()


class RequestUidLogFilter(logging.Filter):
    """모든 로그 줄에 request_uid를 끼워 넣는다(자바 MDC 흉내).

    [주의] 값이 없어도 반드시 채운다. 포맷에 `%(request_uid)s`가 있는데 속성이 없으면 그 줄이 통째로 사라진다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_uid = get_request_uid() or "-"
        return True
