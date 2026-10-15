"""문자열 정규화, 숫자 마스킹, 한국어 금액 파싱·표기 같은 공용 함수."""
from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def norm_ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def mask_numbers(text: str) -> str:
    """숫자를 <NUM>으로 가린다. 숫자만 바뀐 문단이 같은 문단으로 정렬되게 하기 위함."""
    return NUM_RE.sub("<NUM>", norm_ws(text))


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(norm_ws(text).encode("utf-8")).hexdigest()[:n]


def sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(norm_ws(text)) if s]


def truncate(text: str, n: int = 90) -> str:
    text = norm_ws(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def to_number(s: str) -> float:
    return float(s.replace(",", ""))


# ---- 금액 -------------------------------------------------------------------
_KRW_RE = re.compile(
    r"(?:(?P<jo>\d[\d,]*(?:\.\d+)?)\s*조\s*)?"
    r"(?:(?P<eok>\d[\d,]*(?:\.\d+)?)\s*억\s*)?"
    r"(?:(?P<man>\d[\d,]*(?:\.\d+)?)\s*만\s*)?"
    r"원"
)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_krw(text: str) -> list[tuple[str, float]]:
    """'1조 120억원', '405억원', '톤당 1,980만원' 같은 표현을 (원문, 원 단위 값) 목록으로."""
    out = []
    for m in _KRW_RE.finditer(text):
        if not any(m.group(g) for g in ("jo", "eok", "man")):
            continue
        val = 0.0
        if m.group("jo"):
            val += to_number(m.group("jo")) * 1e12
        if m.group("eok"):
            val += to_number(m.group("eok")) * 1e8
        if m.group("man"):
            val += to_number(m.group("man")) * 1e4
        out.append((m.group(0).strip(), val))
    return out


def parse_pct(text: str) -> list[float]:
    return [float(x) for x in _PCT_RE.findall(text)]


def format_krw(won: float) -> str:
    """원 단위 금액을 '1조 120억원', '405억원' 형태로 (억원 단위 반올림)."""
    sign = "-" if won < 0 else ""
    eok = round(abs(won) / 1e8)
    if eok == 0:
        man = round(abs(won) / 1e4)
        return f"{sign}{man:,}만원"
    jo, rest = divmod(eok, 10_000)
    if jo:
        return f"{sign}{jo:,}조 {rest:,}억원" if rest else f"{sign}{jo:,}조원"
    return f"{sign}{rest:,}억원"


def josa(word: str, pair: str) -> str:
    """받침에 맞는 조사. pair 예: '은는', '이가', '을를', '으로로'."""
    if not word:
        return pair[0]
    ch = word[-1]
    has_final = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    if pair == "으로로":
        final_rieul = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 == 8
        return "로" if (not has_final or final_rieul) else "으로"
    return pair[0] if has_final else pair[1]
