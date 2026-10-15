// 백엔드 DTO와 1:1로 맞춘 타입 (docs/CONTRACT.md §2~§6). 필드를 임의로 더하거나 빼지 않는다 —
// 여기가 어긋나면 컴파일은 통과하고 화면만 조용히 빈다.
// 리포트 본문(RadarReport)은 ai-server/radar/schemas.py가 정본이다. 기존 필드는 snake_case,
// §6에서 더한 필드는 camelCase다(계약 그대로). 새 필드는 아직 안 채워진 리포트가 있으므로 선택(?)으로 둔다.

export interface ApiResponse<T> {
  success: boolean;
  data?: T | null;
  error?: { code: string; message: string; details?: unknown } | null;
  requestId: string;
  timestamp: string;
}

// ---- 인증 (§3.1) ----
export type Role = "JUNIOR_ANALYST" | "SENIOR_MANAGER";
export interface LoginUser {
  userId: string;
  name: string;
  role: Role;
  scopes: string[];
}
export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  user: LoginUser;
}
export interface RefreshResponse {
  accessToken: string;
}

// ---- 공통 페이지 (Spring Data Page 직렬화) ----
export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
}

// ---- 분석 요청 (§3.2) ----
export type ReprtCode = "11011" | "11012" | "11013" | "11014";
export type AnalysisStatus = "CREATED" | "RUNNING" | "COMPLETED" | "FAILED" | "BLOCKED";
export interface AnalysisRequestDto {
  id: number;
  userId: string;
  company: string;
  corpCode: string | null;
  corpName: string | null;
  bsnsYear: number;
  reprtCode: ReprtCode | string;
  query: string | null;
  scope: string[];
  status: AnalysisStatus;
  jobId: string | null;
  reportId: number | null;
  demoFaultInjection: boolean;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}
export interface CreateAnalysisRequest {
  company: string;
  bsnsYear: number;
  reprtCode: ReprtCode;
  query?: string;
  demoFaultInjection?: boolean;
}
export interface ExecuteResponse {
  requestId: number;
  jobId: string;
  status: "RUNNING";
}

// ---- Job (§4 JobStatus, Spring /job 프록시) ----
export interface AgentExecution {
  agentId: string;
  stepOrder: number;
  status: string;
  durationMs: number | null;
  errorMessage: string | null;
  summary: string | null;
}
export type JobStep = "PLANNING" | "DISCLOSURE" | "FINANCIAL" | "REVIEW" | "WRITING" | "DONE";
export interface JobStatus {
  jobId: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  progress: number;
  currentStep: JobStep | string | null;
  result: { report?: RadarReport; error?: string } | null;
  agentExecutions: AgentExecution[];
}

// ---- 리포트 (§3.3) ----
export type ApprovalStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";
export interface ReportDto {
  id: number;
  requestId: number;
  title: string;
  summary: string;
  approvalStatus: ApprovalStatus;
  publicationId: string | null;
  body: RadarReport;
  disclaimer: string;
  createdAt: string;
  updatedAt: string;
}
export interface ReportEditRequest {
  itemId: string;
  value: string;
}

// ---- 발행 (§3.4) ----
export type PublicationStatus = "PENDING" | "PUBLISHED" | "REJECTED" | "EXPIRED" | "FAILED" | "SUPERSEDED";
export interface PublicationDto {
  publicationId: string;
  reportId: number;
  corpCode: string;
  corpName: string;
  periodLabel: string;
  title: string;
  version: number;
  supersedesId: string | null;
  contentHash: string;
  status: PublicationStatus;
  submittedBy: string;
  decidedBy: string | null;
  decidedAt: string | null;
  comment: string | null;
  createdAt: string;
  decisionRequiredBy: string;
}
export interface SubmitPublicationRequest {
  reportId: number;
  comment?: string;
}

// ---- 관리 (§3.6) ----
export interface KillSwitchDto {
  killSwitchActive: boolean;
  reason: string | null;
  toggledBy: string | null;
  since: string | null;
}
export interface GuardrailEventDto {
  id: number;
  type: string;
  severity: string;
  requestUid: string | null;
  userId: string | null;
  detectedIssues: string | null;
  blocked: boolean;
  createdAt: string;
}
export interface AuditLogDto {
  id: number;
  type: string;
  requestUid: string | null;
  userId: string | null;
  agentId: string | null;
  requestId: number | null;
  payloadJson: string | null;
  createdAt: string;
}
export interface LlmProvider {
  name: string;
  model: string;
  status: "healthy" | "available" | "blocked" | "unreachable";
  type: "local" | "external";
}
export interface LlmProviders {
  active: string;
  providers: LlmProvider[];
}

// =====================================================================
// 리포트 본문 RadarReport (§6, ai-server/radar/schemas.py)
// =====================================================================
export type EditType = "신설" | "삭제" | "수치 수정" | "표현 수정";
export type Topic = "위험·소송" | "사업·시장" | "거래" | "기타";
export type Level = "인과 명시" | "관련 맥락" | "확인 불가";
export type VStatus = "통과" | "재작성 후 통과" | "반려" | "검토 필요";

export interface Check {
  name: string;
  status: "pass" | "fail" | "warn";
  detail: string;
}
export interface Verification {
  status: VStatus;
  checks: Check[];
  judge?: string | null;
}
export interface ParaRef {
  pid: string;
  section_path: string;
  text: string;
  sentence?: string | null;
}
export interface DiffOp {
  op: "eq" | "ins" | "del";
  text: string;
}
export interface NumberChange {
  old: string | null;
  new: string | null;
}
export interface ChangeItem {
  id: string;
  section_key: string;
  section_path: string;
  edit_type: EditType;
  topic: Topic;
  summary: string;
  summary_before_rewrite?: string | null;
  old: ParaRef[];
  new: ParaRef[];
  similarity: number | null;
  diff: DiffOp[];
  numbers: NumberChange[];
  importance: number;
  in_target_section: boolean;
  flags: string[];
  duplicates: string[];
  verification: Verification;
}
export interface TableCell {
  row: string;
  column: string;
  old: string | null;
  new: string | null;
  kind: "changed" | "row_added" | "row_removed";
}
export interface TableChange {
  id: string;
  section_key: string;
  section_path: string;
  title: string;
  unit: string | null;
  old_id: string | null;
  new_id: string | null;
  cells: TableCell[];
  note: string | null;
}

// §6.2 계산식·출처
export type SourceKind = "재무 API" | "원문 표" | "원문 문단" | "시세" | "계산" | "업종 피어";
export interface Source {
  kind: SourceKind;
  label: string;
  rceptNo?: string;
  pid?: string;
  field?: string;
  url?: string;
}
export interface FormulaInput {
  name: string;
  value: number | null;
  unit: string;
  source?: Source;
  note?: string;
}
export interface Formula {
  id: string;
  label: string;
  expr: string;
  inputs: FormulaInput[];
  result: number | null;
  unit: string;
  status: "계산됨" | "계산 안 함";
  reason?: string;
  notes: string[];
}

export interface Account {
  key: string;
  account_id: string | null;
  account_nm: string;
  sj_div: string | null;
  basis: string;
  current: number;
  prior: number;
  delta: number;
  yoy_pct: number | null;
  is_key: boolean;
  flags: string[];
  robust_z: number | null;
  peer_n: number;
  formulas?: Formula[];
}
export interface Attempt {
  attempt: number;
  status: string;
  reason: string;
  statement: string;
  fault_injected?: boolean;
}
export interface Relation {
  account_key: string;
  account_nm: string;
  direction: "증가" | "감소" | "변동 없음";
  yoy_pct: number | null;
  current: number;
  prior: number;
  level: Level;
  statement: string;
  statement_before_rewrite?: string | null;
  reason_clause: string | null;
  why: string;
  evidence: ParaRef[];
  numeric_claims: Record<string, unknown>[];
  verification: Verification;
  attempts: Attempt[];
}
export interface NodeRun {
  node: string;
  label: string;
  round: number;
  started_ms: number;
  ended_ms: number;
  status: "ok" | "rejected" | "error";
  note: string;
}
export interface ParseStats {
  rcept_no: string;
  files: string[];
  chosen_file: string;
  encoding_declared: string | null;
  encoding_used: string;
  mode: "strict" | "recover";
  amp_fixed: number;
  cr_fixed: number;
  fake_tags_escaped: number;
  cell_counts: Record<string, number>;
  sections: number;
  paragraphs: number;
  tables: number;
  warnings: string[];
}
export interface Filing {
  rcept_no: string;
  report_nm: string;
  rcept_dt: string;
  bsns_year: number;
  reprt_code: string;
  url: string;
}
export interface ReviewEvent {
  at: string;
  actor: string;
  action: string;
  item_id?: string | null;
  detail: string;
}
export interface Review {
  status: "검토 대기" | "승인됨" | "수정 요청";
  reviewer?: string | null;
  decided_at?: string | null;
  comment?: string | null;
  events: ReviewEvent[];
}
export interface MetaCompany {
  corp_code?: string;
  corp_name?: string;
  stock_code?: string;
  induty?: string;
  [k: string]: unknown;
}
export interface Meta {
  analysis_id: string;
  request_uid: string | null;
  created_at: string;
  company: MetaCompany;
  current: Filing;
  prior: Filing;
  source: string;
  fs_div: string;
  embedder: string;
  llm: string;
  pipeline_version: string;
  graph_engine: string;
  demo_fault_injection: boolean;
  sample_data: boolean;
  disclaimer: string;
}
export interface ReportMetrics {
  changes_by_type?: Record<string, number>;
  changes_by_topic?: Record<string, number>;
  relations_by_level?: Record<string, number>;
  verification?: Record<string, number>;
  verify_rounds?: number;
  source_calls?: number;
  llm_usage?: { calls?: number; input_tokens?: number; output_tokens?: number; schema_failures?: number; fallbacks?: number };
  llm_cost_estimate_usd?: number;
  llm_cost_note?: string;
  elapsed_ms?: number;
  [k: string]: unknown;
}

// §6.1 Agent 래퍼 필드
export interface ToolCall {
  tool: string;
  args: Record<string, unknown> | unknown;
  resultSummary: string;
  agentId: string;
}
export interface ReportAgent {
  agentId: string;
  stepOrder: number;
  status: string;
  durationMs: number | null;
  summary: string | null;
}

// §6.3 사업 지표
export type BusinessKind = "부문 매출" | "수주" | "생산능력·가동률";
export type BusinessRowStatus = "검산 통과" | "검산 불일치" | "검산 불가";
export interface BusinessValue {
  name: string;
  unit: string;
  prior: number | null;
  current: number | null;
  yoyPct: number | null;
}
export interface BusinessRow {
  label: string;
  status: BusinessRowStatus;
  values: BusinessValue[];
  checks: Check[];
}
export interface BusinessGroup {
  kind: BusinessKind;
  title: string;
  unit: string | null;
  sectionPath: string;
  priorPid: string | null;
  currentPid: string | null;
  checks: Check[];
  rows: BusinessRow[];
  formulas: Formula[];
}
export interface Business {
  groups: BusinessGroup[];
  summary: { passed: number; failed: number; unchecked: number };
  note: string;
}

// §6.4 지배구조
export interface Shareholder {
  name: string;
  relation: string;
  stockKind: string;
  beginShares: number | null;
  beginPct: number | null;
  endShares: number | null;
  endPct: number | null;
  change: "신규" | "증가" | "감소" | "전량 처분" | "변동 없음";
  deltaPct: number | null;
}
export interface Executive {
  name: string;
  position: string;
  registered: string | boolean;
  fullTime: string | boolean;
  duty: string;
  change: "신규 선임" | "퇴임" | "직위 변경" | "유지";
  priorPosition: string | null;
}
export interface Investment {
  name: string;
  purpose: string;
  beginPct: number | null;
  endPct: number | null;
  bookValue: number | null;
  change: "신규" | "처분" | "지분 증가" | "지분 감소" | "변동 없음";
  corpCode: string | null;
}
export interface GraphNode {
  id: string;
  label: string;
  kind: "company" | "shareholder" | "person" | "investee";
  corpCode: string | null;
}
export interface GraphEdge {
  from: string;
  to: string;
  pct: number | null;
  label: string;
}
export interface Governance {
  rceptNo: string;
  priorRceptNo: string | null;
  shareholders: Shareholder[];
  executives: Executive[];
  investments: Investment[];
  changes: { kind: "주주" | "임원" | "출자"; text: string }[];
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  note: string;
}

// §6.5 시장 지표
export interface Valuation {
  asOf: string | null;
  marketSource: "sample" | "data.go.kr" | null;
  fsDiv: "CFS" | "OFS";
  annual: { year: number; rceptNo: string };
  interim: { year: number; reprtCode: string; rceptNo: string } | null;
  price: { basDt: string; close: number; listedShares: number; marketCap: number } | null;
  prices: { d: string; c: number }[];
  metrics: Formula[];
  notes: string[];
}

export interface RadarReport {
  meta: Meta;
  parse: Record<string, ParseStats>;
  accounts: Account[];
  changes: ChangeItem[];
  tables: TableChange[];
  relations: Relation[];
  timeline: NodeRun[];
  review: Review;
  metrics: ReportMetrics;
  // §6.1
  title?: string;
  summary?: string;
  citations?: string[];
  toolCalls?: ToolCall[];
  reviewPassed?: boolean;
  reviewIssues?: string[];
  generatedAt?: string;
  agents?: ReportAgent[];
  // §6.3~6.5
  business?: Business | null;
  governance?: Governance | null;
  valuation?: Valuation | null;
}

// ---- 기업 (§3.5, §6.6) ----
export interface CompanyRow {
  corpCode: string;
  corpName: string;
  stockCode: string;
  induty: string | null;
  hasFilings: boolean;
  revenue: number | null;
  opIncome: number | null;
  opMarginPct: number | null;
  marketCap: number | null;
  per: number | null;
  pbr: number | null;
  basis: string | null;
}
export interface CompanyFiling {
  rceptNo: string;
  reportNm: string;
  rceptDt: string;
  reprtCode: string;
  bsnsYear: number;
  hasDocument: boolean;
}
export interface Financials {
  fsDiv: string;
  columns: string[];
  rows: { account: string; values: (number | null)[]; formulas: Formula[] }[];
}
export interface CompanyProfile {
  company: { corpCode: string; corpName: string; stockCode: string; induty: string | null };
  filings: CompanyFiling[];
  financials: Financials;
  valuation: Valuation | null;
  valuationNote: string | null;
  business: Business | null;
  governance: Governance | null;
  notes: string[];
}
