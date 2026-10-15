"""Moderation 연동. 기본은 꺼져 있다.

외부 Moderation API는 ① 폐쇄망 모드(ALLOW_EXTERNAL_LLM=false)에서 나갈 수 없는 호출이고
② 실습 중 네트워크 사정으로 실패하면 어디까지가 내 코드 문제인지 알 수 없어서 기본 off다.
인터페이스만 만들어 두어, 규칙이 못 잡는 것을 모델이 잡을 자리를 표시한다.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class ModerationChecker(ABC):
    @abstractmethod
    def check(self, text: str) -> Optional[Dict[str, Any]]:
        """판정 결과. 꺼져 있으면 None."""


class NullModerationChecker(ModerationChecker):
    def check(self, text: str) -> Optional[Dict[str, Any]]:
        return None


class OpenAIModerationChecker(ModerationChecker):
    def check(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            from openai import OpenAI
            r = OpenAI(api_key=settings.openai_api_key).moderations.create(
                model="omni-moderation-latest", input=text[:4000]).results[0]
            return {"flagged": r.flagged, "categories": [k for k, v in r.categories.model_dump().items() if v]}
        except Exception:
            # 실패로 정상 요청을 막지 않는다(fail-open). 못 봤다는 사실만 남긴다
            logger.exception("Moderation 호출 실패. 판정 없이 진행한다")
            return {"flagged": False, "categories": [], "error": "moderation_unavailable"}


@lru_cache(maxsize=1)
def get_moderation_checker() -> ModerationChecker:
    if settings.enable_moderation and settings.allow_external_llm:
        return OpenAIModerationChecker()
    return NullModerationChecker()


def is_moderation_active() -> bool:
    """설정값이 아니라 유효 상태. ENABLE_MODERATION=true여도 폐쇄망 모드면 꺼진다."""
    return not isinstance(get_moderation_checker(), NullModerationChecker)
