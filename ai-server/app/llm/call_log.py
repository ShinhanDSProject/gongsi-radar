"""LLM 호출 기록. 5장 Tool Gateway의 호출 로그와 대칭 구조다.
[보안] 프롬프트 전문이 아니라 SHA-256 해시만 남긴다.
       감사 로그 자체가 PII 유출 경로가 되지 않도록 하기 위함이다 (부록 A §6).
9장에서 Audit DB로 영속화하고, 10장에서 llm_invocation_log 테이블로 확장한다.
"""
from __future__ import annotations
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    record_id: str
    provider: str
    model: str
    agent_id: str
    prompt_hash: str                                 # [보안] 전문 대신 해시
    prompt_chars: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: int = 0
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class LLMCallLog:
    """인메모리 + DB. 10장에서 llm_invocation_log에도 남긴다.

    메모리를 없애지 않은 이유는 `ToolGateway._record`와 같다 —
    DB가 죽어도 최근 호출은 볼 수 있어야 하고, 실습에서 편하다.
    기록의 정본은 DB고 메모리는 들여다보는 창이다.
    """

    def __init__(self) -> None:
        self._records: List[LLMCallRecord] = []

    def add(self, record: LLMCallRecord) -> None:
        self._records.append(record)
        logger.info("llm_call %s/%s | agent=%s | %dms | err=%s",
                    record.provider, record.model, record.agent_id,
                    record.duration_ms, record.error)
        # 순환 import를 피하려고 함수 안에서 부른다 (safety.audit → config → llm)
        from ..safety.audit import record_llm_invocation
        record_llm_invocation(
            provider=record.provider, model_name=record.model,
            agent_id=record.agent_id, prompt_hash=record.prompt_hash,
            prompt_chars=record.prompt_chars,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            duration_ms=record.duration_ms, error=record.error,
        )

    def recent(self, limit: int = 50) -> List[LLMCallRecord]:
        return self._records[-limit:]


llm_call_log = LLMCallLog()                          # 전역 인스턴스 (gateway와 같은 패턴)


def _token_counts(response: LLMResult) -> tuple[Optional[int], Optional[int]]:
    """토큰 수를 꺼낸다. provider마다 넣는 자리가 다르다 (10장).

    OpenAI는 `llm_output["token_usage"]`에 담고, Ollama를 비롯한 최근 어댑터는
    메시지의 `usage_metadata`에 담는다. 한 곳만 보면 provider를 바꿨을 때
    조용히 NULL이 되어, 비교표에서 토큰 열만 통째로 비는 일이 생긴다.
    """
    usage = (response.llm_output or {}).get("token_usage") or {}
    if usage:
        return usage.get("prompt_tokens"), usage.get("completion_tokens")
    for batch in response.generations:
        for gen in batch:
            meta = getattr(getattr(gen, "message", None), "usage_metadata", None)
            if meta:
                return meta.get("input_tokens"), meta.get("output_tokens")
    return None, None


class LLMCallLogger(BaseCallbackHandler):
    """AgentExecutor에 붙여 Agent 루프 안의 모든 LLM 호출을 기록한다.

    LangChain이 chat model을 직접 호출하므로 LLMClient.chat()에 로깅을 넣으면
    Agent 실행 중의 호출은 하나도 잡히지 않는다. 그래서 콜백으로 붙인다.
    """

    def __init__(self, *, provider: str, model: str, agent_id: str) -> None:
        self.provider = provider
        self.model = model
        self.agent_id = agent_id
        self._started: float = 0.0
        self._prompt_hash: str = ""
        self._prompt_chars: int = 0

    # chat model은 on_chat_model_start, 일반 LLM은 on_llm_start가 호출된다.
    # 본 과정은 chat model만 쓰지만 둘 다 받아 둔다.
    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any) -> None:
        self._begin("\n".join(str(m.content) for batch in messages for m in batch))

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self._begin("\n".join(prompts))

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        prompt_tokens, completion_tokens = _token_counts(response)
        self._record(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self._record(error=f"{type(error).__name__}: {error}")

    # ---------- 내부 ----------
    def _begin(self, text: str) -> None:
        self._started = time.time()
        self._prompt_chars = len(text)
        self._prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _record(self, **extra: Any) -> None:
        llm_call_log.add(LLMCallRecord(
            record_id=str(uuid.uuid4()),
            provider=self.provider,
            model=self.model,
            agent_id=self.agent_id,
            prompt_hash=self._prompt_hash,
            prompt_chars=self._prompt_chars,
            duration_ms=int((time.time() - self._started) * 1000),
            **extra,
        ))