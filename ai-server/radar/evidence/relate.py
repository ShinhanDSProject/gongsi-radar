"""관련 서술 연결: 수치 변화가 큰 계정마다 회사가 공시 본문에서 무엇이라고 썼는지 찾는다.

근거 수준 3단계
  - 인과 명시: 같은 문장 안에 계정명 + 원인 표지('로 인해', '의 영향으로' 등) + 맞는 증감 방향
  - 관련 맥락: 계정이나 관련어가 나오지만 원인을 직접 밝히지 않음
  - 확인 불가: 대상 섹션에 관련 문단이 없음

문장은 코드가 템플릿으로 만든다(LLM 모드에서는 LLM이 쓰고, 검증은 똑같이 코드가 한다).
"""
from __future__ import annotations

import re

import numpy as np

from radar.config import RELATE_SECTIONS
from radar.parsing.parser import Block, ParsedDoc
from radar.parsing.textutil import format_krw, josa, mask_numbers, sentences

ACCOUNT_TERMS = {
    "매출액": (["매출액", "매출"], ["판매", "출하", "수요", "판매단가", "수주"]),
    "영업이익": (["영업이익", "영업손실"], ["수익성", "원가", "고정비", "판매단가", "가동률", "마진"]),
    "당기순이익": (["당기순이익", "순이익", "당기순손실"], ["법인세"]),
    "매출원가": (["매출원가"], ["원재료", "원가", "구매단가"]),
    "판매비와관리비": (["판매비와관리비", "판관비"], ["인건비", "광고선전비", "운반비"]),
    "금융비용": (["금융비용", "이자비용"], ["차입", "이자", "사채"]),
    "금융수익": (["금융수익", "이자수익"], ["예금", "외환"]),
    "재고자산": (["재고자산"], ["재고"]),
    "기타비용": (["기타비용"], ["손상", "기부금"]),
}
CAUSAL = re.compile(r"(으로\s*인하여|로\s*인하여|으로\s*인해|로\s*인해|의\s*영향으로|영향으로|에\s*힘입어|때문에|때문|에\s*기인하여|에\s*기인)")
DOWN = re.compile(r"(감소|하락|축소|악화|줄어|둔화|적자)")
UP = re.compile(r"(증가|상승|확대|개선|늘어|흑자)")
LEVELS = ("인과 명시", "관련 맥락", "확인 불가")


def terms_for(account_nm: str) -> tuple[list[str], list[str]]:
    return ACCOUNT_TERMS.get(account_nm, ([account_nm], []))


def direction(yoy_pct: float | None) -> str:
    if yoy_pct is None or abs(yoy_pct) < 0.05:
        return "변동 없음"
    return "증가" if yoy_pct > 0 else "감소"


def _dir_ok(sent: str, d: str) -> bool | None:
    up, down = bool(UP.search(sent)), bool(DOWN.search(sent))
    if d == "증가":
        return True if up else (False if down else None)
    if d == "감소":
        return True if down else (False if up else None)
    return None


def assess(account_nm: str, d: str, block: Block) -> dict:
    """한 문단이 한 계정 변화에 대해 어느 수준의 근거인지 판정."""
    strong, weak = terms_for(account_nm)
    best = {"level": "확인 불가", "sentence": None, "clause": None, "why": "관련어 없음"}
    for s in sentences(block.text):
        has_strong = any(t in s for t in strong)
        has_weak = any(t in s for t in weak)
        if not (has_strong or has_weak):
            continue
        m = CAUSAL.search(s)
        dir_ok = _dir_ok(s, d)
        # 원인 표지가 '이 계정'의 변화를 설명하는지: 계정명이 원인 표지 뒤가 아니라 주어 자리에 있어야 함
        subj = next((t for t in strong if re.search(re.escape(t) + r"\s*(?:은|는|이|가)\s", s)), None)
        if has_strong and m and dir_ok is not False and subj and s.index(subj) < m.start():
            return {"level": "인과 명시", "sentence": s, "clause": cause_clause(s, subj, m),
                    "why": f"같은 문장에 계정명('{subj}'), 원인 표지('{m.group(0)}'), 증감 방향이 함께 있음"}
        if best["level"] == "확인 불가":
            hit = next((t for t in strong + weak if t in s), "")
            why = f"관련어('{hit}')는 있으나 이 계정 변화의 원인을 직접 밝히지 않음"
            if dir_ok is False:
                why = f"관련어('{hit}')가 있으나 증감 방향이 반대로 서술됨"
            best = {"level": "관련 맥락", "sentence": s, "clause": None, "why": why}
    return best


def cause_clause(sent: str, subj: str, m: re.Match) -> str | None:
    start = sent.index(subj) + len(subj)
    clause = re.sub(r"^\s*(?:은|는|이|가)\s*", "", sent[start:m.start()]).strip()
    clause = re.sub(r"\s*(?:으로|로)$", "", clause)  # '증가로 인해'의 '로'는 표지 쪽에 남는 경우 대비
    return clause or None


def candidates(doc: ParsedDoc, account_nm: str, d: str, embedder, k: int = 5,
               exclude: set[str] | None = None) -> list[tuple[Block, dict, float]]:
    """대상 섹션 문단 중 상위 k개(근거 수준 우선, 그다음 유사도)."""
    blocks = [b for b in doc.paragraphs()
              if b.section_key.startswith(RELATE_SECTIONS) and b.id not in (exclude or set())]
    if not blocks:
        return []
    strong, weak = terms_for(account_nm)
    query = f"{account_nm} {d} " + " ".join(strong + weak)
    emb = embedder.encode([mask_numbers(query)] + [mask_numbers(b.text) for b in blocks])
    sims = emb[1:] @ emb[0]
    scored = []
    for b, s in zip(blocks, sims):
        a = assess(account_nm, d, b)
        if a["level"] == "확인 불가":
            continue
        rank = {"인과 명시": 2, "관련 맥락": 1}[a["level"]]
        scored.append((b, a, float(s) + rank))
    scored.sort(key=lambda x: -x[2])
    return scored[:k]


def amount_phrase(acct: dict) -> str:
    nm, cur, prior, y = acct["account_nm"], acct["current"], acct["prior"], acct["yoy_pct"]
    d = direction(y)
    cur_s = format_krw(cur)
    if d == "변동 없음":
        return f"{nm}{josa(nm, '은는')} {cur_s}{josa(cur_s, '으로로')} 전년과 비슷했다."
    pr_s = format_krw(prior)
    return f"{nm}{josa(nm, '은는')} {pr_s}에서 {cur_s}{josa(cur_s, '으로로')} {abs(y):.1f}% {d}했다."


def compose(acct: dict, level: str, clause: str | None) -> str:
    head = amount_phrase(acct)
    if level == "인과 명시":
        if clause:
            return f"{head} 회사는 원인으로 ‘{clause}’{josa(clause, '을를')} 들었다."
        return f"{head} 회사는 공시 본문에서 원인을 직접 밝혔다(인용 참고)."
    if level == "관련 맥락":
        return f"{head} 대상 섹션에 관련 서술은 있지만, 회사가 이 변화의 원인을 직접 밝히지는 않았다."
    return f"{head} 분석 대상 섹션에서 관련 서술을 찾지 못했다."


def numeric_claims(acct: dict) -> list[dict]:
    return [
        {"account": acct["account_nm"], "kind": "prior", "value": acct["prior"], "unit": "원"},
        {"account": acct["account_nm"], "kind": "current", "value": acct["current"], "unit": "원"},
        {"account": acct["account_nm"], "kind": "yoy_pct", "value": acct["yoy_pct"], "unit": "%"},
    ]


def rule_relate(acct: dict, doc: ParsedDoc, embedder, exclude: set[str]) -> dict:
    d = direction(acct["yoy_pct"])
    cands = candidates(doc, acct["account_nm"], d, embedder, exclude=exclude)
    if not cands:
        return {"level": "확인 불가", "evidence": [], "clause": None, "why": "대상 섹션에 관련 문단 없음",
                "statement": compose(acct, "확인 불가", None)}
    top_level = cands[0][1]["level"]
    chosen = [c for c in cands if c[1]["level"] == top_level][:2]
    b, a, _ = chosen[0]
    return {
        "level": top_level,
        "evidence": [{"pid": cb.id, "section_path": cb.section_path, "text": cb.text, "sentence": ca["sentence"]}
                     for cb, ca, _ in chosen],
        "clause": a["clause"], "why": a["why"],
        "statement": compose(acct, top_level, a["clause"]),
    }


def top_candidates_for_llm(acct: dict, doc: ParsedDoc, embedder, exclude: set[str], k: int = 6) -> list[Block]:
    """LLM 모드: 규칙 판정과 무관하게 유사도 상위 k개 문단을 후보로 넘긴다."""
    blocks = [b for b in doc.paragraphs()
              if b.section_key.startswith(RELATE_SECTIONS) and b.id not in exclude]
    if not blocks:
        return []
    strong, weak = terms_for(acct["account_nm"])
    query = f"{acct['account_nm']} {direction(acct['yoy_pct'])} " + " ".join(strong + weak)
    emb = embedder.encode([mask_numbers(query)] + [mask_numbers(b.text) for b in blocks])
    order = np.argsort(-(emb[1:] @ emb[0]))[:k]
    return [blocks[i] for i in order]
