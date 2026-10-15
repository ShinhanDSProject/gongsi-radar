"""사용자별 Tool 호출 상한. 슬라이딩 윈도우 1분.

막으려는 것은 과부하가 아니라 패턴이다 — 인젝션에 걸린 Agent가 같은 호출을 반복하는 신호.
[주의] 프로세스 안 카운터라 AI 서버를 두 대로 늘리면 상한이 두 배가 된다. 운영에서는 Redis 등으로 옮긴다.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

_WINDOW_SEC = 60.0
_calls: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


class RateLimitExceeded(Exception):
    """Tool Gateway·라우터가 429로 바꾼다."""


def check(user_id: str, limit: int) -> None:
    if limit <= 0:
        return
    now = time.time()
    with _lock:                                  # LangChain이 sync Tool을 스레드풀에서 돌린다
        window = _calls[user_id]
        while window and now - window[0] > _WINDOW_SEC:
            window.popleft()
        if len(window) >= limit:
            raise RateLimitExceeded(f"분당 Tool 호출 한도 초과: {len(window)}/{limit} (user={user_id})")
        window.append(now)


def reset() -> None:
    with _lock:
        _calls.clear()
