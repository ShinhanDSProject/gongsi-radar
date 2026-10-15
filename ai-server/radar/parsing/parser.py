"""DART 정기보고서 원문(document.xml ZIP) 파서.

원문은 정상적인 XML이 아니다. 이 파서는 알려진 함정을 하나씩 처리하고, 처리한 내용을 숫자로 남긴다.
조용히 텍스트를 버리지 않는 것이 원칙이다: 엄격 파싱이 실패하면 복구 모드로 넘어가되,
잃어버린 글자 수를 경고로 기록한다.

  1. 본문 파일 선택: ZIP 안의 감사보고서({rcept_no}_00760.xml 등)가 아니라 {rcept_no}.xml
  2. 인코딩: utf-8 시도 → 실패 시 cp949. 선언과 실제가 다르면 경고
  3. 최소 수리: '&cr;' → 줄바꿈, 이스케이프 안 된 '&' → '&amp;', 한글 이름의 가짜 태그 → 텍스트
  4. 표 셀: TD/TH뿐 아니라 TE/TU까지 수집
  5. TITLE 기준 섹션 분할, 문단과 표 분리, 해시 기반 문단 ID
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import asdict, dataclass, field

from lxml import etree

from radar.parsing.textutil import norm_ws, short_hash

CELL_TAGS = ("TD", "TH", "TE", "TU")
_DECL_RE = re.compile(rb'<\?xml[^>]*encoding="([^"]+)"', re.I)
_XML_DECL_TEXT = re.compile(r"^\s*<\?xml[^>]*\?>")
_STRAY_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_FAKE_TAG = re.compile(r"<(/?)([^\x00-\x7f][^<>]*)>")
_UNIT_RE = re.compile(r"^\(?\s*단위\s*[:：]")
_ROMAN = re.compile(r"^([IVXLC]+)\.\s*")
_ARABIC = re.compile(r"^(\d+)\.\s*")
_HANGUL_IDX = re.compile(r"^([가-하])\.\s*")


@dataclass
class Section:
    key: str
    title: str
    path: str
    level: int
    parent: str | None
    order: int


@dataclass
class Block:
    id: str
    kind: str  # "p" | "table"
    section_key: str
    section_path: str
    order: int
    text: str
    header: list[str] | None = None
    rows: list[list[str]] | None = None
    unit: str | None = None


@dataclass
class ParsedDoc:
    rcept_no: str
    files: list[str]
    chosen_file: str
    encoding_declared: str | None
    encoding_used: str
    mode: str  # "strict" | "recover"
    fixes: dict = field(default_factory=dict)
    cell_counts: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def paragraphs(self, section_key: str | None = None) -> list[Block]:
        return [b for b in self.blocks if b.kind == "p" and (section_key is None or b.section_key == section_key)]

    def tables(self, section_key: str | None = None) -> list[Block]:
        return [b for b in self.blocks if b.kind == "table" and (section_key is None or b.section_key == section_key)]

    def by_id(self) -> dict[str, Block]:
        return {b.id: b for b in self.blocks}

    def stats(self) -> dict:
        return {
            "rcept_no": self.rcept_no, "files": self.files, "chosen_file": self.chosen_file,
            "encoding_declared": self.encoding_declared, "encoding_used": self.encoding_used, "mode": self.mode,
            "amp_fixed": self.fixes.get("amp", 0), "cr_fixed": self.fixes.get("cr", 0),
            "fake_tags_escaped": self.fixes.get("fake_tags", 0), "cell_counts": self.cell_counts,
            "sections": len(self.sections), "paragraphs": len(self.paragraphs()), "tables": len(self.tables()),
            "warnings": self.warnings,
        }

    def to_dict(self) -> dict:
        return asdict(self)


class ParseError(RuntimeError):
    pass


# ---- 1. 본문 파일 선택 ----------------------------------------------------------
def choose_main_file(names: list[str], rcept_no: str) -> str:
    xmls = [n for n in names if n.lower().endswith(".xml")]
    exact = f"{rcept_no}.xml"
    if exact in xmls:
        return exact
    # 첨부(감사보고서 등)는 접수번호 뒤에 _00760 같은 꼬리가 붙는다
    plain = [n for n in xmls if not re.search(r"_\d{5}\.xml$", n)]
    if plain:
        return plain[0]
    if xmls:
        raise ParseError(f"본문 파일을 찾지 못했습니다(첨부만 있음): {xmls}")
    raise ParseError("ZIP 안에 XML 파일이 없습니다.")


# ---- 2. 인코딩 ----------------------------------------------------------------
def decode(raw: bytes) -> tuple[str, str | None, str, list[str]]:
    warnings = []
    m = _DECL_RE.search(raw[:300])
    declared = m.group(1).decode("ascii", "ignore").lower() if m else None
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "cp949"):
        try:
            text = raw.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        text, used = raw.decode("cp949", errors="replace"), "cp949(replace)"
        warnings.append("utf-8과 cp949 모두 실패해 깨진 글자를 대체 문자로 바꿨습니다.")
    if declared and declared.replace("-", "") not in used.replace("-", ""):
        if not (declared in ("euc-kr", "ks_c_5601-1987") and used == "cp949"):
            warnings.append(f"선언된 인코딩({declared})과 실제 인코딩({used})이 다릅니다.")
    return text, declared, used, warnings


# ---- 3. 최소 수리 ---------------------------------------------------------------
def repair(text: str) -> tuple[str, dict]:
    fixes = {}
    text, fixes["cr"] = re.subn(r"&cr;", "\n", text)
    text, nbsp = re.subn(r"&nbsp;", " ", text)
    fixes["nbsp"] = nbsp
    text, fixes["amp"] = _STRAY_AMP.subn("&amp;", text)
    text, fixes["fake_tags"] = _FAKE_TAG.subn(lambda m: f"&lt;{m.group(1)}{m.group(2)}&gt;", text)
    text = _XML_DECL_TEXT.sub('<?xml version="1.0" encoding="utf-8"?>', text, count=1)
    return text, fixes


def _visible_len(xml_text: str) -> int:
    return len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", xml_text)))


def parse_tree(text: str) -> tuple[etree._Element, str, list[str]]:
    data = text.encode("utf-8")
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(recover=False, huge_tree=True, resolve_entities=False))
        return root, "strict", []
    except etree.XMLSyntaxError as e:
        root = etree.fromstring(data, parser=etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False))
        before = _visible_len(text)
        after = len(re.sub(r"\s+", "", "".join(root.itertext()))) if root is not None else 0
        lost = max(0, before - after)
        return root, "recover", [f"엄격 파싱 실패({e.msg}, line {e.lineno}) → 복구 모드. 텍스트 약 {lost:,}자 손실 가능."]


# ---- 4·5. 섹션·문단·표 -----------------------------------------------------------
def _text(el) -> str:
    return norm_ws("".join(el.itertext()))


def _section_key(title: str, level: int, parent_key: str | None, idx: int) -> str:
    if level == 1:
        m = _ROMAN.match(title)
        return m.group(1) if m else f"S{idx}"
    base = parent_key or "S"
    m = _ARABIC.match(title) or _HANGUL_IDX.match(title)
    return f"{base}-{m.group(1)}" if m else f"{base}-s{idx}"


class _Walker:
    def __init__(self, rcept_no: str):
        self.rcept_no = rcept_no
        self.sections: list[Section] = []
        self.blocks: list[Block] = []
        self.cell_counts = {t: 0 for t in CELL_TAGS}
        self._order = 0
        self._ids: dict[str, int] = {}

    def _uid(self, base: str) -> str:
        n = self._ids.get(base, 0) + 1
        self._ids[base] = n
        return base if n == 1 else f"{base}-{n}"

    def section(self, el, level: int, parent: Section | None, idx: int):
        title_el = el.find("TITLE")
        title = _text(title_el) if title_el is not None else f"(제목 없음 {idx})"
        key = _section_key(title, level, parent.key if parent else None, idx)
        path = f"{parent.path} > {title}" if parent else title
        sec = Section(key=key, title=title, path=path, level=level, parent=parent.key if parent else None,
                      order=len(self.sections))
        self.sections.append(sec)
        self._content(el, sec, level)

    def _content(self, el, sec: Section, level: int):
        pending_unit = None
        child_idx = 0
        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "TITLE":
                continue
            if tag.startswith("SECTION-"):
                child_idx += 1
                self.section(child, level + 1, sec, child_idx)
            elif tag == "TABLE-GROUP":
                for sub in child:
                    st = sub.tag if isinstance(sub.tag, str) else ""
                    if st == "P" and _UNIT_RE.match(_text(sub)):
                        pending_unit = _text(sub)
                    elif st == "P":
                        self._para(sub, sec)
                    elif st == "TABLE":
                        self._table(sub, sec, pending_unit)
                        pending_unit = None
            elif tag == "P":
                t = _text(child)
                if _UNIT_RE.match(t):
                    pending_unit = t
                else:
                    self._para(child, sec)
            elif tag == "TABLE":
                self._table(child, sec, pending_unit)
                pending_unit = None

    def _para(self, el, sec: Section):
        text = _text(el)
        if not text:
            return
        self._order += 1
        bid = self._uid(f"{self.rcept_no}:{sec.key}:{short_hash(text)}")
        self.blocks.append(Block(id=bid, kind="p", section_key=sec.key, section_path=sec.path,
                                 order=self._order, text=text))

    def _table(self, el, sec: Section, unit: str | None):
        rows, header = [], None
        for tr in el.iter("TR"):
            cells = []
            for c in tr:
                ct = c.tag if isinstance(c.tag, str) else ""
                if ct in CELL_TAGS:
                    self.cell_counts[ct] += 1
                    cells.append(_text(c))
            if not cells:
                continue
            in_head = tr.getparent() is not None and tr.getparent().tag == "THEAD"
            if header is None and (in_head or all(c.tag == "TH" for c in tr if isinstance(c.tag, str))):
                header = cells
            else:
                rows.append(cells)
        flat = " | ".join(" / ".join(r) for r in ([header] if header else []) + rows)
        self._order += 1
        bid = self._uid(f"{self.rcept_no}:{sec.key}:T{short_hash(flat)}")
        self.blocks.append(Block(id=bid, kind="table", section_key=sec.key, section_path=sec.path,
                                 order=self._order, text=flat, header=header, rows=rows, unit=unit))


def parse_document_xml(text: str, rcept_no: str) -> tuple[list[Section], list[Block], dict, str, list[str]]:
    repaired, fixes = repair(text)
    root, mode, warnings = parse_tree(repaired)
    body = root.find(".//BODY") if root is not None else None
    if body is None:
        raise ParseError("BODY 요소를 찾지 못했습니다.")
    w = _Walker(rcept_no)
    idx = 0
    for el in body:
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "SECTION-1":
            idx += 1
            w.section(el, 1, None, idx)
    return w.sections, w.blocks, {"fixes": fixes, "cells": w.cell_counts}, mode, warnings


def parse_filing_zip(data: bytes, rcept_no: str) -> ParsedDoc:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        # OpenDART는 오류 시 ZIP 대신 XML/JSON 오류 메시지를 돌려준다
        snippet = data[:200].decode("utf-8", "replace")
        raise ParseError(f"ZIP이 아닙니다(오류 응답일 수 있음): {snippet}") from e
    names = z.namelist()
    chosen = choose_main_file(names, rcept_no)
    text, declared, used, enc_warnings = decode(z.read(chosen))
    sections, blocks, info, mode, warnings = parse_document_xml(text, rcept_no)
    doc = ParsedDoc(rcept_no=rcept_no, files=names, chosen_file=chosen, encoding_declared=declared,
                    encoding_used=used, mode=mode, fixes=info["fixes"], cell_counts=info["cells"],
                    sections=sections, blocks=blocks, warnings=enc_warnings + warnings)
    missing = info["cells"].get("TE", 0) + info["cells"].get("TU", 0)
    if missing:
        doc.warnings.append(f"TE/TU 셀 {missing}개를 수집했습니다(TD/TH만 읽었다면 오류 없이 누락됐을 셀).")
    return doc
