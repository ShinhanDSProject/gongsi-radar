"""표 diff. 표는 LLM에 보내지 않고 행 단위 규칙으로만 비교한다.

행은 첫 번째 셀(항목명)로, 열은 머리글로 맞춘다. 같은 기수 열(예: 제11기)이 두 보고서에 모두 있으면
그 열의 값을 비교해 전기 수치 재작성 여부를 확인한다.
"""
from __future__ import annotations

import difflib

from radar.diff.align import match_sections
from radar.parsing.parser import Block, ParsedDoc
from radar.parsing.textutil import norm_ws


def _key(s: str) -> str:
    return norm_ws(s).replace(" ", "")


def _pair_tables(o_ts: list[Block], n_ts: list[Block]) -> list[tuple[Block | None, Block | None]]:
    pairs, used = [], set()
    for nt in n_ts:
        best, best_r = None, 0.0
        for k, ot in enumerate(o_ts):
            if k in used:
                continue
            r = difflib.SequenceMatcher(None, " ".join(ot.header or []), " ".join(nt.header or [])).ratio()
            if r > best_r:
                best, best_r = k, r
        if best is not None and best_r >= 0.5:
            used.add(best)
            pairs.append((o_ts[best], nt))
        else:
            pairs.append((None, nt))
    pairs += [(ot, None) for k, ot in enumerate(o_ts) if k not in used]
    return pairs


def diff_table(ot: Block, nt: Block) -> tuple[list[dict], str | None]:
    oh, nh = ot.header or [], nt.header or []
    common = [h for h in nh[1:] if h in oh[1:]]
    note = None
    if common and len(common) < len(nh) - 1:
        # 기수 열이 한 칸씩 밀린 요약재무 표: 겹치는 기수만 비교(재작성 확인)
        cols = [(h, oh.index(h), nh.index(h)) for h in common]
        note = f"겹치는 기간({', '.join(common)}) 값을 비교해 전기 수치 재작성 여부를 확인했습니다."
    elif common:
        cols = [(h, oh.index(h), nh.index(h)) for h in common]
    else:
        cols = [(nh[i] if i < len(nh) else f"열{i}", i, i) for i in range(1, min(len(oh), len(nh)))]
    o_rows = {_key(r[0]): r for r in ot.rows or [] if r}
    n_rows = {_key(r[0]): r for r in nt.rows or [] if r}
    cells = []
    for k, nr in n_rows.items():
        orow = o_rows.get(k)
        if orow is None:
            cells.append({"row": nr[0], "column": "", "old": None, "new": " / ".join(nr[1:]), "kind": "row_added"})
            continue
        for h, oi, ni in cols:
            ov = orow[oi] if oi < len(orow) else None
            nv = nr[ni] if ni < len(nr) else None
            if norm_ws(ov or "") != norm_ws(nv or ""):
                cells.append({"row": nr[0], "column": h, "old": ov, "new": nv, "kind": "changed"})
    for k, orow in o_rows.items():
        if k not in n_rows:
            cells.append({"row": orow[0], "column": "", "old": " / ".join(orow[1:]), "new": None, "kind": "row_removed"})
    if note and not any(c["kind"] == "changed" for c in cells):
        note += " 재작성된 값은 없습니다."
    elif note:
        note += " 값이 다른 셀이 있어 재작성 여부를 검토해야 합니다."
    return cells, note


def diff_tables(old: ParsedDoc, new: ParsedDoc) -> list[dict]:
    out = []
    for os_, ns in match_sections(old, new):
        if not (os_ and ns):
            continue
        for ot, nt in _pair_tables(old.tables(os_.key), new.tables(ns.key)):
            if ot is None or nt is None:
                b = nt or ot
                out.append({"id": f"T{len(out) + 1}", "section_key": b.section_key, "section_path": b.section_path,
                            "title": " / ".join(b.header or []), "unit": b.unit,
                            "old_id": ot.id if ot else None, "new_id": nt.id if nt else None,
                            "cells": [], "note": "새로 생긴 표" if nt else "사라진 표"})
                continue
            cells, note = diff_table(ot, nt)
            if cells or note:
                out.append({"id": f"T{len(out) + 1}", "section_key": nt.section_key, "section_path": nt.section_path,
                            "title": " / ".join(nt.header or []), "unit": nt.unit, "old_id": ot.id, "new_id": nt.id,
                            "cells": cells, "note": note})
    return out
