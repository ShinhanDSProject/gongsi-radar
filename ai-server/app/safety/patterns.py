"""PII 정규식과 Prompt Injection 패턴(Quant-X 부록 A §4.2 · §5.1을 공시 도메인에 맞춘 것).

[보안] 규칙 기반이라 우회가 가능하다. "주민번호 900101 다시 1234567"처럼 끊어 쓰면 잡지 못한다.
       그래서 이것만으로 안전하다고 말하지 않는다. Tool Gateway의 Scope 검사, Core Zone의 키 분리,
       발행 전 사람 결재가 함께 있어야 한다.

공시 도메인에서 더한 것:
  - 공시 원문에는 날짜(2025-09-17)·사업자번호 모양의 숫자가 흔하다. 날짜는 계좌로 오인하지 않는다.
  - TOOL_ABUSE에 "발행·승인·공시 제출"을 더했다. Agent에게 결재를 시키려는 요구다.
"""
from __future__ import annotations

import re
from typing import List, Optional, Pattern, Tuple

# 계좌번호 정규식이 삼키는 날짜(4-2-2). 예외를 안 두면 날짜가 든 정상 질문이 전부 막힌다
_DATE_LIKE = re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$")

# (코드, 정규식, 마스킹 태그, 예외 패턴). 순서가 결과를 바꾼다 — ACCT가 CARD·PHONE·BIZ를 삼키므로 뒤에 둔다
PII_PATTERNS: List[Tuple[str, Pattern[str], str, Optional[Pattern[str]]]] = [
    ("RRN", re.compile(r"\d{6}-?[1-4]\d{6}"), "[RRN_MASKED]", None),
    ("CARD", re.compile(r"\d{4}-\d{4}-\d{4}-\d{4}"), "[CARD_MASKED]", None),
    ("PHONE", re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "[PHONE_MASKED]", None),
    ("BIZ", re.compile(r"\d{3}-\d{2}-\d{5}"), "[BIZ_MASKED]", None),
    ("ACCT", re.compile(r"\d{2,6}-\d{2,6}-\d{2,6}"), "[ACCT_MASKED]", _DATE_LIKE),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL_MASKED]", None),
]

# Prompt Injection. 문장이 아니라 '의도'를 잡는 패턴이라 오탐이 난다. 일부는 WARNING으로만 둔다
INJECTION_PATTERNS: List[Tuple[str, Pattern[str], str]] = [
    ("IGNORE_PREV",
     re.compile(r"(이전|위의|앞의|모든)[^.\n]{0,10}(지시|명령|규칙|프롬프트)[^.\n]{0,10}"
                r"(무시|잊|해제)|ignore\s+(all\s+)?(previous|prior|above)", re.I),
     "이전 지시를 무시하라는 요구"),
    ("REVEAL_PROMPT",
     re.compile(r"(시스템\s*프롬프트|system\s*prompt|너의?\s*(지시문|규칙|설정))[^.\n]{0,15}"
                r"(보여|알려|출력|공개|말해)|reveal\s+your\s+(prompt|instructions)", re.I),
     "시스템 프롬프트를 요구"),
    ("ROLE_CHANGE",
     re.compile(r"(너는|당신은|지금부터)[^.\n]{0,20}(개발자|관리자|admin|DAN|결재자)[^.\n]{0,10}(이다|야|입니다|처럼)"
                r"|act\s+as\s+(a\s+)?(developer|admin|root)", re.I),
     "역할을 바꾸라는 요구"),
    ("TOOL_ABUSE",
     re.compile(r"(발행|승인|결재|공시\s*제출|주문|매수|매도)[^.\n]{0,15}(해\s*줘|해줘|처리해|진행해|넣어|실행)"),
     "Agent에게 결재·발행을 시키려는 요구"),
    ("SYSTEM_TAG",
     re.compile(r"</?(system|assistant|im_start|im_end)\b", re.I),
     "대화 역할 태그를 흉내낸 문자열"),
]

# 차단까지 가는 Injection 코드. 나머지는 경고만 남기고 통과시킨다
BLOCKING_INJECTION_CODES = {"IGNORE_PREV", "REVEAL_PROMPT", "SYSTEM_TAG"}
