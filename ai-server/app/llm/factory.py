"""LLM_PROVIDER 하나로 provider를 고른다. Agent 코드는 이 모듈만 보며 구현체를 알지 못한다.

[보안] 외부 호출 차단을 이 한 자리에서 한다. 어댑터가 각자 자기를 막게 두면 provider가 늘 때마다
       같은 검사를 베껴 넣어야 하고, 한 군데만 빠뜨려도 폐쇄망에 구멍이 난다.
런타임 전환(switch_provider)도 기동 시와 같은 검사(_ensure_allowed)를 탄다.

공시레이더에는 LLM을 부르는 자리가 두 종류다.
  ① Agent·Manager·Writer — LangChain chat model(get_llm_client)
  ② radar 파이프라인 안의 구조화 호출(변경 요약·관련 서술 판정·2단 판정·재작성) — get_radar_llm
두 자리가 같은 provider 스위치를 따른다. ②는 OpenAI 호환 /chat/completions를 쓰므로 Ollama(/v1)도 그대로 붙는다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict

import httpx

from ..config import settings
from .base import LLMClient

logger = logging.getLogger(__name__)

PROVIDERS = ("openai", "ollama", "mock")
EXTERNAL_PROVIDERS = {"openai"}          # 인터넷으로 나가는 provider


def _ensure_allowed(provider: str) -> None:
    # 폐쇄망에서 외부 provider를 고르면 여기서 죽는다. 조용히 다른 걸로 바꿔 주지 않는다 —
    # "막힌 줄 알았는데 나가고 있었다"와 "내가 고르지 않은 모델이 답했다"가 제일 나쁘다
    if provider in EXTERNAL_PROVIDERS and not settings.allow_external_llm:
        raise RuntimeError(f"ALLOW_EXTERNAL_LLM=false 인데 LLM_PROVIDER={provider} 다. "
                           "폐쇄망 모드에서는 ollama 또는 mock 을 쓴다.")


@lru_cache(maxsize=None)
def get_llm_client() -> LLMClient:
    provider = settings.llm_provider.lower()
    _ensure_allowed(provider)
    if provider == "openai":
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter()
    if provider == "ollama":
        from .ollama_adapter import OllamaAdapter
        return OllamaAdapter()
    if provider == "mock":
        from .mock_adapter import MockAdapter
        return MockAdapter()
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {settings.llm_provider}")


def _model_of(provider: str) -> str:
    if provider == "ollama":
        return settings.ollama_model
    if provider == "mock":
        return "mock-model"
    return settings.llm_model


def active_model_name() -> str:
    return _model_of(settings.llm_provider.lower())


def get_radar_llm(agent_id: str):
    """radar 파이프라인용 LLM. mock이면 규칙 모드(RuleLLM) — 결과가 결정적이다.

    호출 기록: radar의 OpenAICompatLLM은 post 함수를 주입받는다. 여기서 감싼 post가 모든 호출을
    llm_invocation_log에 남긴다(프롬프트는 해시만). Agent 쪽 콜백 기록과 같은 테이블·같은 축이다.
    """
    from radar.llm import OpenAICompatLLM, RuleLLM

    provider = settings.llm_provider.lower()
    _ensure_allowed(provider)
    if provider == "mock":
        return RuleLLM()
    if provider == "ollama":
        base, key, model = settings.ollama_base_url.rstrip("/") + "/v1", None, settings.ollama_model
    else:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY가 비어 있다. LLM_PROVIDER=mock 으로 전환하거나 키를 설정한다.")
        base, key, model = "https://api.openai.com/v1", settings.openai_api_key, settings.llm_model

    def post(url: str, payload: dict) -> dict:
        from .call_log import LLMCallRecord, llm_call_log
        text = json.dumps(payload.get("messages", []), ensure_ascii=False)
        started, err, resp = time.time(), None, {}
        try:
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            r = httpx.post(url, json=payload, headers=headers, timeout=settings.agent_timeout_seconds)
            r.raise_for_status()
            resp = r.json()
            return resp
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            raise ValueError(err) from e        # radar가 ValueError를 재시도·규칙 폴백으로 처리한다
        finally:
            usage = (resp or {}).get("usage") or {}
            llm_call_log.add(LLMCallRecord(
                record_id=hashlib.sha1(f"{time.time()}{url}".encode()).hexdigest()[:12], provider=provider,
                model=model, agent_id=agent_id, prompt_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                prompt_chars=len(text), prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                duration_ms=int((time.time() - started) * 1000), error=err))

    llm = OpenAICompatLLM(base, key, model, model, post=post, max_retries=1)
    llm.name = f"{provider}:{model}"
    return llm


def _ollama_status() -> str:
    """Ollama 생존 확인. 로컬이라 물어봐도 된다 — openai는 확인 요청 자체가 외부 호출이라 묻지 않는다."""
    try:
        httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=1.5)
        return "healthy"
    except httpx.HTTPError:
        return "unreachable"


def list_providers() -> Dict[str, Any]:
    """막힌 외부 provider도 목록에서 지우지 않고 blocked로 보인다 — "없다"와 "막았다"를 구분한다."""
    rows = []
    for name in PROVIDERS:
        if name in EXTERNAL_PROVIDERS:
            status, ptype = ("blocked" if not settings.allow_external_llm else "available"), "external"
        else:
            status, ptype = (_ollama_status() if name == "ollama" else "healthy"), "local"
        rows.append({"name": name, "model": _model_of(name), "status": status, "type": ptype})
    return {"active": settings.llm_provider.lower(), "providers": rows}


def switch_provider(name: str) -> str:
    """런타임 전환. 메모리의 settings만 바꾼다 — 재기동하면 .env 값으로 돌아간다.
    임베딩은 건드리지 않는다(바꾸면 벡터 차원이 달라져 재색인이 따라온다)."""
    provider = name.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(f"지원하지 않는 provider: {name} (가능: {', '.join(PROVIDERS)})")
    _ensure_allowed(provider)
    settings.llm_provider = provider
    get_llm_client.cache_clear()           # 진행 중인 실행은 이미 잡은 클라이언트로 끝난다
    logger.info("llm provider switched: %s (model=%s)", provider, active_model_name())
    return provider
