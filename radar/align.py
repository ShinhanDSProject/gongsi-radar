"""섹션·문단 정렬과 변경 유형 판정 (LLM에 무엇을 넣지 않을지 정하는 계층).

1. 섹션은 번호를 뗀 제목 경로로 맞추고, 남은 것은 같은 상위 섹션 안에서 퍼지 매칭한다.
2. 문단은 숫자를 <NUM>으로 가린 뒤 임베딩하고, 문단 순서를 지키는 동적 계획법으로 1:1 정렬한다.
3. 정렬된 짝 옆의 짝 없는 문단은 '분할·병합'(1:N)인지 확인한다.
4. 그래도 남은 문단 중 아주 비슷한 것은 '이동'으로 다시 짝짓는다.
5. 남은 문단은 신설·삭제, 짝은 동일·수치 수정·표현 수정으로 판정한다.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import numpy as np

from .parser import Block, ParsedDoc, Section
from .textutil import mask_numbers, norm_ws

_TITLE_PREFIX = re.compile(r"^\s*(?:[IVXLC]+|\d+|[가-하])\.\s*")


@dataclass
class RawChange:
    section_key: str
    section_path: str
    edit_type: str  # 신설 | 삭제 | 수치 수정 | 표현 수정 | 동일
    old: list[Block] = field(default_factory=list)
    new: list[Block] = field(default_factory=list)
    similarity: float | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def old_text(self) -> str:
        return " ".join(b.text for b in self.old)

    @property
    def new_text(self) -> str:
        return " ".join(b.text for b in self.new)


# ---- 섹션 매칭 -----------------------------------------------------------------
def _norm_title(t: str) -> str:
    return re.sub(r"\s+", "", _TITLE_PREFIX.sub("", t))


def _norm_path(sec: Section, secs: dict[str, Section]) -> str:
    parts, cur = [], sec
    while cur is not None:
        parts.append(_norm_title(cur.title))
        cur = secs.get(cur.parent) if cur.parent else None
    return "/".join(reversed(parts))


def match_sections(old: ParsedDoc, new: ParsedDoc) -> list[tuple[Section | None, Section | None]]:
    o_by_key = {s.key: s for s in old.sections}
    n_by_key = {s.key: s for s in new.sections}
    o_paths = {_norm_path(s, o_by_key): s for s in old.sections}
    n_paths = {_norm_path(s, n_by_key): s for s in new.sections}
    pairs, used_old = [], set()
    unmatched_new = []
    for p, ns in n_paths.items():
        if p in o_paths:
            pairs.append((o_paths[p], ns))
            used_old.add(o_paths[p].key)
        else:
            unmatched_new.append((p, ns))
    for p, ns in unmatched_new:  # 같은 상위 경로 안에서 퍼지 매칭
        parent = p.rsplit("/", 1)[0] if "/" in p else ""
        best, best_r = None, 0.0
        for op, os_ in o_paths.items():
            if os_.key in used_old:
                continue
            o_parent = op.rsplit("/", 1)[0] if "/" in op else ""
            if o_parent != parent:
                continue
            r = difflib.SequenceMatcher(None, op, p).ratio()
            if r > best_r:
                best, best_r = os_, r
        if best is not None and best_r >= 0.8:
            pairs.append((best, ns))
            used_old.add(best.key)
        else:
            pairs.append((None, ns))
    for s in old.sections:
        if s.key not in used_old:
            pairs.append((s, None))
    return pairs


# ---- 문단 정렬 -----------------------------------------------------------------
def _monotone_align(S: np.ndarray, tau: float) -> list[tuple[int, int]]:
    """순서를 지키면서 (유사도 - tau) 합이 최대가 되는 1:1 짝."""
    n, m = S.shape
    f = np.zeros((n + 1, m + 1))
    back = np.zeros((n + 1, m + 1), dtype=np.int8)  # 0: 대각, 1: 위, 2: 왼쪽
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, arg = f[i - 1, j], 1
            if f[i, j - 1] > best:
                best, arg = f[i, j - 1], 2
            s = S[i - 1, j - 1]
            if s >= tau and f[i - 1, j - 1] + (s - tau) + 1e-9 > best:
                best, arg = f[i - 1, j - 1] + (s - tau) + 1e-9, 0
            f[i, j], back[i, j] = best, arg
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        a = back[i, j]
        if a == 0:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif a == 1:
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


def _classify(old: list[Block], new: list[Block]) -> str:
    ot, nt = norm_ws(" ".join(b.text for b in old)), norm_ws(" ".join(b.text for b in new))
    if ot == nt:
        return "동일"
    if mask_numbers(ot) == mask_numbers(nt):
        # 기준연도만 한 해 넘어간 문단(2024년 → 2025년)은 변경으로 보지 않는다
        return "수치 수정" if number_changes(ot, nt) else "동일"
    return "표현 수정"


def _grams(text: str) -> set[str]:
    t = re.sub(r"[\s\W]+", "", mask_numbers(text).replace("<NUM>", "#"))
    return {t[k:k + 2] for k in range(len(t) - 1)}


def _coverage(base: str, parts: str) -> float:
    g = _grams(base)
    return len(g & _grams(parts)) / len(g) if g else 0.0


def align_paragraphs(old_ps: list[Block], new_ps: list[Block], embedder, th: dict,
                     section_key: str, section_path: str) -> list[RawChange]:
    if not old_ps and not new_ps:
        return []
    if not old_ps:
        return [RawChange(section_key, section_path, "신설", [], [b]) for b in new_ps]
    if not new_ps:
        return [RawChange(section_key, section_path, "삭제", [b], []) for b in old_ps]

    o_emb = embedder.encode([mask_numbers(b.text) for b in old_ps])
    n_emb = embedder.encode([mask_numbers(b.text) for b in new_ps])
    S = o_emb @ n_emb.T
    pairs = _monotone_align(S, th["match"])
    groups: list[dict] = [{"o": [i], "n": [j], "flags": []} for i, j in pairs]
    used_o = {i for i, _ in pairs}
    used_n = {j for _, j in pairs}

    def sim_text(a: str, b: str) -> float:
        e = embedder.encode([mask_numbers(a), mask_numbers(b)])
        return float(e[0] @ e[1])

    # 분할(1:N)·병합(N:1): 이웃 문단을 붙였을 때 원 문단 내용을 눈에 띄게 더 덮으면 한 묶음으로 본다.
    # 임베딩 유사도는 붙인 문단의 새 단어 때문에 오히려 떨어질 수 있어, 문자 bigram 포함률로 판단한다.
    for g in groups:
        i, j = g["o"][0], g["n"][0]
        for nb in (j + 1, j - 1):
            if 0 <= nb < len(new_ps) and nb not in used_n and S[i, nb] >= th["part"]:
                seq = sorted([j, nb])
                cat = " ".join(new_ps[k].text for k in seq)
                if _coverage(old_ps[i].text, cat) - _coverage(old_ps[i].text, new_ps[j].text) >= th["split_gain"]:
                    g["n"] = seq
                    g["flags"].append("분할")
                    used_n.add(nb)
                    break
        for nb in (i + 1, i - 1):
            if 0 <= nb < len(old_ps) and nb not in used_o and S[nb, j] >= th["part"]:
                seq = sorted([i, nb])
                cat = " ".join(old_ps[k].text for k in seq)
                if _coverage(new_ps[j].text, cat) - _coverage(new_ps[j].text, old_ps[i].text) >= th["split_gain"]:
                    g["o"] = seq
                    g["flags"].append("병합")
                    used_o.add(nb)
                    break

    # 이동: 순서가 바뀐 문단
    cand = sorted(((S[i, j], i, j) for i in range(len(old_ps)) if i not in used_o
                   for j in range(len(new_ps)) if j not in used_n), reverse=True)
    for s, i, j in cand:
        if s < th["move"]:
            break
        if i in used_o or j in used_n:
            continue
        groups.append({"o": [i], "n": [j], "flags": ["이동"]})
        used_o.add(i)
        used_n.add(j)

    # 같은 자리: 앞뒤로 짝지어진 문단 사이에 남은 문단끼리는 유사도가 다소 낮아도 같은 문단을 고쳐 쓴 것으로 본다
    anchors = sorted((max(g["o"]), max(g["n"]), min(g["o"]), min(g["n"])) for g in groups if "이동" not in g["flags"])
    bounds = [(-1, -1, -1, -1)] + anchors + [(len(old_ps), len(new_ps), len(old_ps), len(new_ps))]
    for (pi, pj, _, _), (_, _, ni, nj) in zip(bounds, bounds[1:]):
        o_gap = [i for i in range(pi + 1, ni) if i not in used_o]
        n_gap = [j for j in range(pj + 1, nj) if j not in used_n]
        for s, i, j in sorted(((S[i, j], i, j) for i in o_gap for j in n_gap), reverse=True):
            if s < th["slot"]:
                break
            if i in used_o or j in used_n:
                continue
            groups.append({"o": [i], "n": [j], "flags": ["같은 자리"]})
            used_o.add(i)
            used_n.add(j)

    out: list[RawChange] = []
    for g in groups:
        o = [old_ps[k] for k in g["o"]]
        n = [new_ps[k] for k in g["n"]]
        sim = sim_text(" ".join(b.text for b in o), " ".join(b.text for b in n)) if (len(o) > 1 or len(n) > 1) \
            else float(S[g["o"][0], g["n"][0]])
        et = _classify(o, n)
        if et == "동일" and g["flags"]:
            et = "표현 수정"
        out.append(RawChange(section_key, section_path, et, o, n, round(sim, 3), g["flags"]))
    for i, b in enumerate(old_ps):
        if i not in used_o:
            out.append(RawChange(section_key, section_path, "삭제", [b], []))
    for j, b in enumerate(new_ps):
        if j not in used_n:
            out.append(RawChange(section_key, section_path, "신설", [], [b]))
    out.sort(key=lambda c: (c.new[0].order if c.new else 10_000 + c.old[0].order))
    return out


def diff_documents(old: ParsedDoc, new: ParsedDoc, embedder, th: dict) -> list[RawChange]:
    embedder.fit([mask_numbers(b.text) for b in old.paragraphs() + new.paragraphs()])
    changes: list[RawChange] = []
    for os_, ns in match_sections(old, new):
        key = (ns or os_).key
        path = (ns or os_).path
        o_ps = old.paragraphs(os_.key) if os_ else []
        n_ps = new.paragraphs(ns.key) if ns else []
        part = align_paragraphs(o_ps, n_ps, embedder, th, key, path)
        if os_ is None:
            for c in part:
                c.flags.append("새 섹션")
        if ns is None:
            for c in part:
                c.flags.append("사라진 섹션")
        changes.extend(part)
    return changes


# ---- 표시용 diff ---------------------------------------------------------------
_TOKEN = re.compile(r"\s+|[^\s]+")
_NUM_UNIT = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)(?!,\d)"   # 숫자 전체를 한 덩어리로
    r"(?:\s*(?P<u>조\s*\d[\d,]*\s*억원|조원|억원|만원|원|%|톤|주|건|개|명|곳|년|월|일))?"
    r"(?(u)|(?![가-힣]))"  # 단위가 없으면 '1심'처럼 한글이 바로 붙은 숫자는 제외
)
_YEAR = re.compile(r"^(\d{4})년$")


def word_diff(a: str, b: str) -> list[dict]:
    at, bt = _TOKEN.findall(a), _TOKEN.findall(b)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, at, bt, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "eq", "text": "".join(at[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "del", "text": "".join(at[i1:i2])})
            if j2 > j1:
                ops.append({"op": "ins", "text": "".join(bt[j1:j2])})
    merged: list[dict] = []
    for o in ops:  # 공백만 있는 eq는 이웃에 붙여 읽기 쉽게
        if merged and merged[-1]["op"] == o["op"]:
            merged[-1]["text"] += o["text"]
        else:
            merged.append(dict(o))
    return merged


def _nums(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", m.group(0)).strip() for m in _NUM_UNIT.finditer(text)]


def _year_roll(o: str | None, n: str | None) -> bool:
    mo, mn = _YEAR.match(o or ""), _YEAR.match(n or "")
    return bool(mo and mn and int(mn.group(1)) - int(mo.group(1)) == 1)


def number_changes(a: str, b: str, keep_year_roll: bool = False) -> list[dict]:
    """두 문단의 숫자(단위 포함) 목록을 정렬해 바뀐 숫자만 짝지어 돌려준다."""
    an, bn = _nums(a), _nums(b)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, an, bn, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        olds, news = an[i1:i2], bn[j1:j2]
        k = min(len(olds), len(news)) if tag == "replace" else 0
        pairs = list(zip(olds[:k], news[:k])) + [(o, None) for o in olds[k:]] + [(None, n) for n in news[k:]]
        for o, n in pairs:
            if not keep_year_roll and _year_roll(o, n):
                continue
            out.append({"old": o, "new": n})
    return out


def phrase_changes(a: str, b: str) -> list[tuple[str | None, str | None]]:
    """어절 단위로 바뀐 구절 목록. 숫자만 바뀐 구절은 number_changes가 맡으므로 뺀다."""
    at, bt = a.split(), b.split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, at, bt, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        o = " ".join(at[i1:i2]) or None
        n = " ".join(bt[j1:j2]) or None
        if o and n and mask_numbers(o) == mask_numbers(n):
            continue
        out.append((o, n))
    return out


def inserted_deleted(a: str, b: str) -> tuple[list[str], list[str]]:
    ins, dels = [], []
    for o in word_diff(a, b):
        t = o["text"].strip()
        if not t:
            continue
        if o["op"] == "ins":
            ins.append(t)
        elif o["op"] == "del":
            dels.append(t)
    return ins, dels
