"""리포트 JSON 계약. Spring Boot·React가 이 스키마를 기준으로 붙는다.

python -m radar schema > docs/report.schema.json 으로 JSON Schema를 뽑을 수 있다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EditType = Literal["신설", "삭제", "수치 수정", "표현 수정"]
Topic = Literal["위험·소송", "사업·시장", "거래", "기타"]
Level = Literal["인과 명시", "관련 맥락", "확인 불가"]
VStatus = Literal["통과", "재작성 후 통과", "반려", "검토 필요"]


class Check(BaseModel):
    name: str
    status: Literal["pass", "fail", "warn"]
    detail: str = ""


class Verification(BaseModel):
    status: VStatus
    checks: list[Check]
    judge: str | None = None


class ParaRef(BaseModel):
    pid: str = Field(description="인용 ID: {rcept_no}:{섹션 키}:{해시 8자리}")
    section_path: str
    text: str
    sentence: str | None = None


class DiffOp(BaseModel):
    op: Literal["eq", "ins", "del"]
    text: str


class NumberChange(BaseModel):
    old: str | None
    new: str | None


class ChangeItem(BaseModel):
    id: str
    section_key: str
    section_path: str
    edit_type: EditType
    topic: Topic
    summary: str
    summary_before_rewrite: str | None = None
    old: list[ParaRef]
    new: list[ParaRef]
    similarity: float | None
    diff: list[DiffOp]
    numbers: list[NumberChange]
    importance: float
    in_target_section: bool
    flags: list[str]
    duplicates: list[str]
    verification: Verification


class TableCell(BaseModel):
    row: str
    column: str
    old: str | None
    new: str | None
    kind: Literal["changed", "row_added", "row_removed"]


class TableChange(BaseModel):
    id: str
    section_key: str
    section_path: str
    title: str
    unit: str | None
    old_id: str | None
    new_id: str | None
    cells: list[TableCell]
    note: str | None


class Account(BaseModel):
    key: str
    account_id: str | None
    account_nm: str
    sj_div: str | None
    basis: str
    current: int
    prior: int
    delta: int
    yoy_pct: float | None
    is_key: bool
    flags: list[str]
    robust_z: float | None
    peer_n: int


class Attempt(BaseModel):
    attempt: int
    status: str
    reason: str
    statement: str
    fault_injected: bool = False


class Relation(BaseModel):
    account_key: str
    account_nm: str
    direction: Literal["증가", "감소", "변동 없음"]
    yoy_pct: float | None
    current: int
    prior: int
    level: Level
    statement: str
    statement_before_rewrite: str | None = None
    reason_clause: str | None
    why: str
    evidence: list[ParaRef]
    numeric_claims: list[dict]
    verification: Verification
    attempts: list[Attempt]


class NodeRun(BaseModel):
    node: str
    label: str
    round: int
    started_ms: int
    ended_ms: int
    status: Literal["ok", "rejected", "error"]
    note: str


class ParseStats(BaseModel):
    rcept_no: str
    files: list[str]
    chosen_file: str
    encoding_declared: str | None
    encoding_used: str
    mode: Literal["strict", "recover"]
    amp_fixed: int
    cr_fixed: int
    fake_tags_escaped: int
    cell_counts: dict[str, int]
    sections: int
    paragraphs: int
    tables: int
    warnings: list[str]


class Filing(BaseModel):
    rcept_no: str
    report_nm: str
    rcept_dt: str
    bsns_year: int
    reprt_code: str
    url: str


class ReviewEvent(BaseModel):
    at: str
    actor: str
    action: str
    item_id: str | None = None
    detail: str = ""


class Review(BaseModel):
    status: Literal["검토 대기", "승인됨", "수정 요청"]
    reviewer: str | None = None
    decided_at: str | None = None
    comment: str | None = None
    events: list[ReviewEvent]


class Meta(BaseModel):
    analysis_id: str
    request_uid: str | None
    created_at: str
    company: dict
    current: Filing
    prior: Filing
    source: str
    fs_div: str
    embedder: str
    llm: str
    pipeline_version: str
    graph_engine: str
    demo_fault_injection: bool
    sample_data: bool
    disclaimer: str


class Report(BaseModel):
    meta: Meta
    parse: dict[str, ParseStats]
    accounts: list[Account]
    changes: list[ChangeItem]
    tables: list[TableChange]
    relations: list[Relation]
    timeline: list[NodeRun]
    review: Review
    metrics: dict
