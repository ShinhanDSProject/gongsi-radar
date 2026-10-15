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


# ---- 계산식·출처 (§6.2) ----------------------------------------------------------------
class Source(BaseModel):
    kind: Literal["재무 API", "원문 표", "원문 문단", "시세", "계산", "업종 피어"]
    label: str
    rceptNo: str | None = None
    pid: str | None = None
    field: str | None = None
    url: str | None = None


class FormulaInput(BaseModel):
    name: str
    value: float | None
    unit: str
    source: Source | None = None
    note: str | None = None


class Formula(BaseModel):
    id: str
    label: str
    expr: str
    inputs: list[FormulaInput]
    result: float | None
    unit: str
    status: Literal["계산됨", "계산 안 함"]
    reason: str | None = Field(default=None, description="계산 안 함일 때 사유(값을 0으로 바꾸지 않음)")
    notes: list[str] = []


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
    formulas: list[Formula] = []


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


# ---- 사업 지표 (§6.3) -----------------------------------------------------------------
class BusinessValue(BaseModel):
    name: str
    unit: str
    prior: float | None
    current: float | None
    yoyPct: float | None


class BusinessRow(BaseModel):
    label: str
    status: Literal["검산 통과", "검산 불일치", "검산 불가"]
    values: list[BusinessValue]
    checks: list[Check]


class BusinessGroup(BaseModel):
    kind: Literal["부문 매출", "수주", "생산능력·가동률"]
    title: str
    unit: str | None
    sectionPath: str
    priorPid: str | None
    currentPid: str | None
    checks: list[Check]
    rows: list[BusinessRow]
    formulas: list[Formula]


class BusinessSummary(BaseModel):
    passed: int
    failed: int
    unchecked: int


class Business(BaseModel):
    groups: list[BusinessGroup]
    summary: BusinessSummary
    note: str


# ---- 지배구조 (§6.4) -------------------------------------------------------------------
class Shareholder(BaseModel):
    name: str
    relation: str
    stockKind: str
    beginShares: int | None
    beginPct: float | None
    endShares: int | None
    endPct: float | None
    change: Literal["신규", "증가", "감소", "전량 처분", "변동 없음"]
    deltaPct: float | None


class Executive(BaseModel):
    name: str
    position: str
    registered: bool
    fullTime: bool
    duty: str
    change: Literal["신규 선임", "퇴임", "직위 변경", "유지"]
    priorPosition: str | None


class Investment(BaseModel):
    name: str
    purpose: str
    beginPct: float | None
    endPct: float | None
    bookValue: int | None
    change: Literal["신규", "처분", "지분 증가", "지분 감소", "변동 없음"]
    corpCode: str | None


class GovernanceChange(BaseModel):
    kind: Literal["주주", "임원", "출자"]
    text: str


class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["company", "shareholder", "person", "investee"]
    corpCode: str | None


class GraphEdge(BaseModel):
    model_config = {"populate_by_name": True}
    from_: str = Field(alias="from")
    to: str
    pct: float | None
    label: str


class GovernanceGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class Governance(BaseModel):
    rceptNo: str
    priorRceptNo: str | None
    shareholders: list[Shareholder]
    executives: list[Executive]
    investments: list[Investment]
    changes: list[GovernanceChange]
    graph: GovernanceGraph
    note: str


# ---- 시장 지표 (§6.5) -------------------------------------------------------------------
class AnnualRef(BaseModel):
    year: int
    rceptNo: str


class InterimRef(BaseModel):
    year: int
    reprtCode: str
    rceptNo: str


class PriceRef(BaseModel):
    basDt: str
    close: float | None
    listedShares: int | None
    marketCap: float | None


class PricePoint(BaseModel):
    d: str
    c: float


class Valuation(BaseModel):
    asOf: str | None
    marketSource: Literal["sample", "data.go.kr"] | None
    fsDiv: Literal["CFS", "OFS"]
    annual: AnnualRef
    interim: InterimRef | None
    price: PriceRef | None
    prices: list[PricePoint]
    metrics: list[Formula] = Field(description="id: market_cap, ttm_revenue, ttm_op, ttm_ni_owner, per_ttm, per_annual, pbr")
    notes: list[str]


# ---- 기업 목록·상세 (§6.6, Spring /api/companies 응답 — 분리 전 /ai/companies. Report에는 들어가지 않음) ----------
class CompanyRow(BaseModel):
    corpCode: str
    corpName: str
    stockCode: str
    induty: str | None
    hasFilings: bool
    revenue: float | None
    opIncome: float | None
    opMarginPct: float | None
    marketCap: float | None
    per: float | None
    pbr: float | None
    basis: str | None


class CompanyInfo(BaseModel):
    corpCode: str
    corpName: str
    stockCode: str
    induty: str | None


class FilingRow(BaseModel):
    rceptNo: str
    reportNm: str
    rceptDt: str
    reprtCode: str
    bsnsYear: int
    hasDocument: bool


class FinancialRow(BaseModel):
    account: str
    values: list[float | None]
    formulas: list[Formula]


class FinancialTable(BaseModel):
    fsDiv: str | None
    columns: list[str]
    rows: list[FinancialRow]


class CompanyProfile(BaseModel):
    company: CompanyInfo
    filings: list[FilingRow]
    financials: FinancialTable
    valuation: Valuation | None
    valuationNote: str | None
    business: Business | None
    governance: Governance | None
    notes: list[str]


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
    # 확장(§6). 예전에 저장한 리포트에는 없으므로 모두 기본값을 둔다. Agent 래퍼 필드(§6.1)는 camelCase
    business: Business | None = None
    governance: Governance | None = None
    valuation: Valuation | None = None
    title: str = ""
    summary: str = ""
    citations: list[str] = []
    toolCalls: list[dict] = Field(default=[], description="{tool, args, resultSummary, agentId}[] (AI 서버가 채움)")
    reviewPassed: bool = True
    reviewIssues: list[str] = []
    generatedAt: str = ""
    agents: list[dict] = Field(default=[], description="{agentId, stepOrder, status, durationMs, summary}[] (AI 서버가 채움)")
