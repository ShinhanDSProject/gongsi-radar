"""Input Filter — 사용자 질문(관심 질문)이 LLM에 닿기 전에 거른다.

순서는 마스킹 → 인젝션 탐지다. 반대로 하면 탐지 결과 문자열에 원본 PII가 섞여 들어간다.
[보안] 마스킹은 '지우는 것'이지 복원 가능한 치환이 아니다. 매핑 테이블이 곧 유출 경로가 된다.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from ..schemas.guardrail import GuardrailResult
from .moderation import get_moderation_checker
from .patterns import BLOCKING_INJECTION_CODES, INJECTION_PATTERNS, PII_PATTERNS


def mask_pii(text: str) -> Tuple[str, List[str]]:
    """PII를 마스킹 태그로 바꾸고 무엇을 찾았는지 돌려준다. 예외 패턴(날짜 등)은 건드리지 않는다."""
    issues: List[str] = []
    masked = text
    for code, pattern, tag, exempt in PII_PATTERNS:
        def _sub(m: "re.Match[str]", _tag=tag, _code=code, _exempt=exempt) -> str:
            if _exempt is not None and _exempt.match(m.group(0)):
                return m.group(0)
            issues.append(f"PII_DETECTED:{_code}")
            return _tag
        masked = pattern.sub(_sub, masked)
    return masked, issues


def detect_injection(text: str) -> List[str]:
    """원문이 아니라 마스킹된 텍스트를 넣는다."""
    return [f"INJECTION:{code}" for code, pattern, _ in INJECTION_PATTERNS if pattern.search(text)]


def check_input(text: str) -> GuardrailResult:
    """입력 한 건을 판정한다. 기록은 부르는 쪽(audit)이 남긴다.

    - PII가 하나라도 있으면 BLOCKED. 공시 분석 질문에 개인 식별 정보가 들어갈 이유가 없다
    - Injection은 코드에 따라 갈린다. 지시 무시·프롬프트 노출·역할 태그는 BLOCKED, 나머지는 WARNING
    """
    masked, pii_issues = mask_pii(text or "")
    injection_issues = detect_injection(masked)
    issues = pii_issues + injection_issues
    blocking = [i for i in injection_issues if i.split(":", 1)[1] in BLOCKING_INJECTION_CODES]
    should_block = bool(pii_issues) or bool(blocking)
    risk = "BLOCKED" if should_block else ("WARNING" if issues else "SAFE")

    moderation = get_moderation_checker().check(masked)
    if moderation and moderation.get("flagged"):
        issues.append("MODERATION_FLAGGED")
        risk, should_block = "BLOCKED", True

    return GuardrailResult(isSafe=(risk == "SAFE"), riskLevel=risk, detectedIssues=issues,
                           filteredText=masked, shouldBlock=should_block, moderation=moderation)
