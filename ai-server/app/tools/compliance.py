"""리포트 초안에서 규정 위반 후보를 찾는 규칙 기반 검사. LLM을 쓰지 않아 같은 입력에는 같은 결과가 나온다.
Risk Reviewer가 초안 검토에 쓰고(Tool), Output Filter가 사용자에게 나가기 직전에 다시 쓴다.

공시 도메인의 금지 표현은 radar/evidence/verify.py의 BANNED(유사투자자문업 금지 광고·금감원 적발 사례 기반)가 정본이다.
여기서는 그 목록을 그대로 RECOMMEND로 묶고, Quant-X의 보장·단정 규칙을 더한다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from radar.evidence.verify import banned_hits

_RULES: List[Tuple[str, str, str]] = [
    ("GUARANTEE", r"(수익|원금|주가)[^.\n]{0,10}(보장|확실|틀림없)", "수익·원금 보장으로 읽힐 수 있는 표현"),
    ("CERTAIN", r"(반드시|무조건|확실히)[^.\n]{0,10}(상승|하락|오를|내릴|급등|급락|개선|회복)", "단정적 전망"),
]

_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*\s*(원|%|배|억|조)")


def check_compliance_rules(text: str, citation_count: int = 0) -> Dict[str, Any]:
    """초안 텍스트에서 규정 위반 후보를 찾는다. Scope 검사는 Tool Gateway가 이미 마쳤다."""
    text = text or ""
    issues: List[Dict[str, str]] = []
    for code, pattern, message in _RULES:
        for m in re.finditer(pattern, text):
            start = max(0, m.start() - 15)
            issues.append({"code": code, "message": message,
                           "snippet": text[start:m.end() + 15].replace("\n", " ")})
    for hit in banned_hits(text):           # 예: '매수(매매 권유)', '저평가(가치판단)'
        issues.append({"code": "RECOMMEND", "message": f"투자 판단으로 읽힐 수 있는 표현: {hit}", "snippet": hit})
    # 수치를 제시하면서 인용이 하나도 없으면 근거 없는 단정으로 본다
    if citation_count == 0 and _NUMBER_RE.search(text):
        issues.append({"code": "NO_SOURCE", "message": "수치를 제시했지만 인용이 하나도 없다", "snippet": ""})
    return {"passed": not issues, "issues": issues[:10]}
