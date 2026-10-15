"""변경 문단의 주제 분류·요약(규칙 버전)과 인젝션 의심 탐지, 중요도 점수.

LLM이 설정되어 있으면 요약은 LLM이 쓰고(llm.py), 이 모듈의 규칙 결과는 폴백과 비교 기준으로 쓴다.
"""
from __future__ import annotations

import re

from radar.diff.align import number_changes, phrase_changes
from radar.parsing.textutil import sentences, truncate

TOPICS = ("위험·소송", "사업·시장", "거래", "기타")
EDIT_TYPES = ("신설", "삭제", "수치 수정", "표현 수정")

_LEX = {
    "위험·소송": {"소송": 3, "피고": 3, "원고": 3, "청구": 2, "분쟁": 3, "특허": 2, "제재": 3, "우발": 3, "계류": 3,
              "손해배상": 3, "판결": 3, "항소": 3, "위험": 1.5, "헤지": 1.5, "환율": 1},
    "거래": {"특수관계": 3, "최대주주": 3, "대주주": 3, "계열회사": 3, "대여": 2, "지급보증": 3, "담보": 2},
    "사업·시장": {"시장": 1, "수요": 1.5, "매출": 1.5, "고객": 1, "제품": 1, "생산": 1, "판매": 1, "공장": 1,
              "원재료": 1, "수주": 1.5, "출하": 1, "증설": 1.5, "가격": 1, "단가": 1, "영업이익": 1.5, "투자": 1},
}
_SECTION_PRIOR = {"XI": ("위험·소송", 2), "X": ("거래", 2), "II-5": ("위험·소송", 1)}

# 공시 문서에 섞여 들어온 '지시문' 패턴(간접 프롬프트 인젝션)
_INJECTION = re.compile(
    r"(이전의?\s*(?:모든\s*)?지시|지시(?:를|사항을)?\s*무시|무시하고|시스템\s*프롬프트|요약하는\s*AI|AI\s*(?:시스템|모델)은"
    r"|출력하(?:십시오|라|세요)|ignore\s+(?:all\s+)?previous|system\s+prompt)",
    re.I,
)


def topic_of(text: str, section_key: str) -> str:
    scores = {t: 0.0 for t in TOPICS}
    for t, words in _LEX.items():
        for w, s in words.items():
            if w in text:
                scores[t] += s
    for prefix, (t, s) in _SECTION_PRIOR.items():
        if section_key == prefix or section_key.startswith(prefix + "-"):
            scores[t] += s
    best = max(scores, key=lambda t: (scores[t], -TOPICS.index(t)))
    return best if scores[best] >= 1.5 else "기타"


def injection_suspected(text: str) -> bool:
    return bool(_INJECTION.search(text or ""))


def rule_summary(edit_type: str, old_text: str, new_text: str, flags: list[str]) -> str:
    if edit_type == "신설":
        return "신설: " + truncate(sentences(new_text)[0] if new_text else "", 110)
    if edit_type == "삭제":
        return "삭제: " + truncate(sentences(old_text)[0] if old_text else "", 110)
    nums = number_changes(old_text, new_text)
    num_txt = ", ".join(f"{n['old'] or '(없음)'} → {n['new'] or '(없음)'}" for n in nums[:4])
    if edit_type == "수치 수정":
        return f"수치 변경: {num_txt}" if num_txt else "수치 변경"
    parts = []
    if "분할" in flags:
        parts.append("한 문단이 두 문단으로 나뉨")
    if "병합" in flags:
        parts.append("두 문단이 한 문단으로 합쳐짐")
    for o, n in phrase_changes(old_text, new_text)[:3]:
        if o and n:
            parts.append(f"‘{truncate(o, 40)}’ → ‘{truncate(n, 50)}’")
        elif n:
            parts.append(f"추가 ‘{truncate(n, 60)}’")
        else:
            parts.append(f"삭제 ‘{truncate(o, 50)}’")
    if num_txt:
        parts.append(f"수치 {num_txt}")
    return "표현 변경: " + "; ".join(parts) if parts else "표현 변경"


INJECTION_SUMMARY = "지시문으로 의심되는 문장이 새로 들어왔습니다. 데이터로만 취급했고, 내용을 요약하거나 따르지 않았습니다."

_TOPIC_W = {"위험·소송": 3.0, "거래": 2.5, "사업·시장": 2.0, "기타": 1.0}
_EDIT_W = {"신설": 3.0, "삭제": 2.5, "표현 수정": 2.0, "수치 수정": 1.5}


_CORE_RISK = re.compile(r"(소송|피고|분쟁|특허침해|제재|손해배상|지급보증|자금\s*대여|대여하였)")


def importance(topic: str, edit_type: str, in_target: bool, injection: bool, text: str = "") -> float:
    """정렬용 점수. 인젝션 의심은 검토자가 먼저 보도록 맨 위."""
    if injection:
        return 99.0
    bonus = (0.5 if in_target else 0.0) + (1.0 if _CORE_RISK.search(text) else 0.0)
    return round(_TOPIC_W[topic] * _EDIT_W[edit_type] + bonus, 2)
