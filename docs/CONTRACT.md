# 공시레이더 — 계층 간 계약 (구현 기준 문서)

> Quant-X(금융 풀스택 과정 11장 완성본)의 아키텍처를 공시 도메인으로 옮긴 구조다.
> 참고 구현: `~/workspace/shinhan/quant-x` (읽기 전용 참고. 수정하지 않는다).
> 이 문서는 4개 계층이 서로 맞춰야 하는 이름·경로·필드를 정한다. 여기와 다르게 만들면 다른 계층이 조용히 깨진다.

## 0. 도메인 매핑 (Quant-X → 공시레이더)

| Quant-X | 공시레이더 |
|---|---|
| 리서치 요청(`research_request`) | 분석 요청(`analysis_request`): 회사·사업연도·보고서 종류(+선택 관심 질문) |
| 리서치 보고서(`research_report`) | 분석 리포트(`analysis_report`): 전년 대비 공시 비교 리포트 |
| Worker 4종(Research·Market·Risk·Report) | `disclosure_analyst`(공시 비교) · `financial_analyst`(재무·사업지표·시장) · `risk_reviewer`(검증·지배구조·소송) · `report_writer`(리포트 작성) + Manager |
| RAG: 사내 리포트·공시 | RAG: DART 원문 문단(신뢰도 HIGH) + 외부 인용 문단(MEDIUM) |
| Market Data Tool | 공시·재무·시세·지배구조 Tool (DART 형태 샘플 / OpenDART / 공공데이터포털 시세) |
| Core Zone: 주문 원장(PENDING→EXECUTED) | Core Zone: **리포트 발행 원장**(PENDING→PUBLISHED) |
| HITL: Senior가 주문 승인 | HITL: Senior가 리포트 발행 승인(자기 요청은 승인 불가) |
| 차단 표현: "수익 보장" | 차단 표현: 매수·매도·목표가·저평가 등 투자 권유·가치판단 (기존 `radar/verify.py BANNED`) |
| PII: 계좌·주민번호 | PII: 주민번호·계좌·카드·전화·사업자번호·이메일 (공시 원문의 개인 정보 포함) |

원칙: **AI는 쓰지 않는다(Write 없음).** 조회·초안까지만. 발행은 사람이 승인해야 Core Zone에 기록된다.
**숫자는 코드가 계산한다.** LLM이 쓴 문장도 코드 검증(`radar/verify.py`)을 통과해야 리포트에 남는다.

## 1. 구성·포트

| 층 | 디렉터리 | 기술 | 포트 |
|---|---|---|---|
| DMZ | `frontend/` | React 18 + TypeScript + Vite 6 + TanStack Query 5 + Tailwind 4 + react-router 6 | 3100 (`/api` → 8180 프록시) |
| Service | `backend/` | Spring Boot 3.3.x, Java 21, Gradle, Security(JWT), JPA, MariaDB | 8180 |
| AI | `ai-server/` | FastAPI, LangChain, LangGraph, Chroma, `radar/`(도메인 라이브러리) | 8100 |
| Core | `core-service/` | FastAPI + SQLite + SQLAlchemy | 9100 |
| LLM | Ollama | `qwen2.5:7b`, 임베딩 `bge-m3` | 11434 |
| DB | Docker `gongsi-mariadb` | MariaDB 11, DB 이름 `gongsi` | 3307 |

브라우저는 Spring Boot만 부른다. FastAPI·Core는 내부 키를 가진 서버끼리만 부른다.

### 1.1 키·계정 (개발 기본값. 운영은 환경변수로 덮어쓴다)

| 이름 | 기본값 | 쓰는 곳 |
|---|---|---|
| `AI_SERVER_API_KEY` | `dev-ai-internal-key` | Spring → FastAPI (`X-Internal-API-Key`) |
| `CORE_API_KEY` | `dev-core-read-key` | FastAPI → Core 조회 (`X-Internal-API-Key`) |
| `CORE_SYSTEM_KEY` | `dev-core-system-key` | Spring → Core 쓰기 (`X-System-Key`). **AI 서버에는 절대 두지 않는다** |
| `JWT_SECRET` | 64바이트 이상 개발용 문자열 | Spring |
| MariaDB root | `root` / `root` | DDL 적용(사람) |
| `gongsi_app` | `app-pass` | Spring·FastAPI 런타임(업무 테이블 RW, 감사 테이블 읽기만, DELETE 없음) |
| `gongsi_audit` | `audit-only-pass` | 감사 기록 전용(감사 테이블 INSERT·SELECT만) |

JDBC: `jdbc:mariadb://localhost:3307/gongsi?useUnicode=true&characterEncoding=utf8`
SQLAlchemy: `mysql+pymysql://gongsi_app:app-pass@localhost:3307/gongsi?charset=utf8mb4`

### 1.2 사용자 (seed, 비밀번호 모두 `password`)

| user_id | 이름 | role | scopes |
|---|---|---|---|
| `analyst_001` | 주니어 김 | `JUNIOR_ANALYST` | `DISCLOSURE_READ`, `MARKET_DATA_READ`, `RAG_READ`, `REPORT_READ` |
| `analyst_002` | 주니어 박 | `JUNIOR_ANALYST` | 위와 같음 |
| `senior_001` | 시니어 이 | `SENIOR_MANAGER` | 위 + `REPORT_WRITE`, `PUBLICATION_READ` |

Scope 의미: `DISCLOSURE_READ` 공시 원문·재무·지배구조 조회 / `MARKET_DATA_READ` 시세·PER·PBR / `RAG_READ` 원문 문단 검색 /
`REPORT_READ` 리포트 조회 / `REPORT_WRITE` 발행 승인·반려 / `PUBLICATION_READ` 발행 원장 조회(Tool).

## 2. 공통 응답 형식 (Spring → 브라우저)

```json
{ "success": true, "data": {}, "error": null, "requestId": "req-uuid", "timestamp": "2026-10-15T12:00:00+09:00" }
{ "success": false, "data": null, "error": { "code": "GUARDRAIL_BLOCKED", "message": "...", "details": null }, "requestId": "...", "timestamp": "..." }
```
모든 응답에 `X-Request-ID` 헤더. ErrorCode: `UNAUTHORIZED 401`, `FORBIDDEN 403`, `NOT_FOUND 404`, `VALIDATION_ERROR 400`,
`GUARDRAIL_BLOCKED 422`, `KILL_SWITCH_ACTIVE 503`, `LLM_PROVIDER_ERROR 502`, `RATE_LIMIT_EXCEEDED 429`, `INTERNAL_ERROR 500`,
`AI_SERVER_UNAVAILABLE 503`, `CORE_PUBLICATION_REJECTED 409`, `CORE_UNAVAILABLE 503`, `REPORT_LOCKED 409`, `SELF_APPROVAL_FORBIDDEN 403`.

## 3. Spring Boot API (`/api`, `Authorization: Bearer <JWT>`)

### 3.1 인증
- `POST /api/auth/login` `{userId, password}` → `{accessToken, refreshToken, user:{userId, name, role, scopes}}`
- `POST /api/auth/refresh` `{refreshToken}` → `{accessToken}` · `POST /api/auth/logout`

### 3.2 분석 요청
- `POST /api/analysis-requests` `{company, bsnsYear, reprtCode, query?, demoFaultInjection?}` → 201 `AnalysisRequestDto`
  - `company`: 종목코드·고유번호·회사명. `reprtCode`: `11011|11012|11013|11014`. `query`(선택, ≤1000자)는 입력 가드레일을 거친다.
- `GET /api/analysis-requests?status=&page=0&size=20` → `Page<AnalysisRequestDto>` (Junior는 자기 것만, Senior는 전체)
- `GET /api/analysis-requests/{id}` · `POST /api/analysis-requests/{id}/execute` → 202 `{requestId, jobId, status:"RUNNING"}`
- `GET /api/analysis-requests/{id}/status` → 갱신된 `AnalysisRequestDto` (FastAPI Job이 COMPLETED면 리포트를 `analysis_report`에 저장하고 요청을 COMPLETED로)
- `GET /api/analysis-requests/{id}/job` → FastAPI `JobStatus` 프록시(소유자 검사)

```ts
AnalysisRequestDto = { id, userId, company, corpCode|null, corpName|null, bsnsYear, reprtCode, query|null, scope:string[],
  status:"CREATED"|"RUNNING"|"COMPLETED"|"FAILED"|"BLOCKED", jobId|null, reportId|null, demoFaultInjection,
  createdAt, startedAt|null, finishedAt|null }
```

### 3.3 리포트
- `GET /api/reports?approvalStatus=&page=` · `GET /api/reports/{id}` → `ReportDto`
- `POST /api/reports/{id}/edits` `{itemId, value}` — 검토자 문구 수정. Spring이 FastAPI `/ai/guardrails/output-check`로 검사 →
  BLOCKED면 422. 통과하면 `body_json`의 해당 항목(`changes[].summary` 또는 `relations[].statement`)을 고치고
  `review.events`에 기록, 감사 로그 `REPORT_EDITED`. 발행 요청 이후(PENDING·PUBLISHED)에는 409 `REPORT_LOCKED`.
```ts
ReportDto = { id, requestId, title, summary, approvalStatus:"DRAFT"|"PENDING"|"APPROVED"|"REJECTED",
  publicationId|null, body: RadarReport, disclaimer, createdAt, updatedAt }
```
`approvalStatus`: 생성 시 `DRAFT` → 발행 요청 `PENDING` → 승인 `APPROVED`(잠김) / 반려 `REJECTED`(다시 수정·재요청 가능).

### 3.4 발행(HITL) — Core Zone 래핑
- `POST /api/publications` `{reportId, comment?}` — 리포트 소유자 또는 Senior. Spring이 `content_hash = SHA-256(body_json 정규화 문자열)`과
  멱등성 키(서버 생성 UUID, `publication_queue`에 먼저 저장)를 만들어 Core `POST /core/publications` 호출 → 201 `PublicationDto`
- `GET /api/publications/pending` (Senior) · `GET /api/publications?corpCode=&status=` (`REPORT_READ`)
- `POST /api/publications/{publicationId}/approve` `{comment?}` (Senior, `@PreAuthorize`) — 요청자와 같은 사람이면 403 `SELF_APPROVAL_FORBIDDEN`.
  Core approve 호출 시 저장해 둔 `content_hash`를 함께 보낸다. 성공 시 리포트 `APPROVED`, `review.status="승인됨"`.
- `POST /api/publications/{publicationId}/reject` `{reason}` (Senior) → 리포트 `REJECTED`
```ts
PublicationDto = { publicationId, reportId, corpCode, corpName, periodLabel, title, version, supersedesId|null, contentHash,
  status:"PENDING"|"PUBLISHED"|"REJECTED"|"EXPIRED"|"FAILED", submittedBy, decidedBy|null, decidedAt|null, comment|null,
  createdAt, decisionRequiredBy }
```

### 3.5 기업 (Spring이 적재 DB·원천에서 직접 계산 — §11)
- `GET /api/companies?q=&limit=50` (`DISCLOSURE_READ`) → `CompanyRow[]`
- `GET /api/companies/{corpCode}` (`DISCLOSURE_READ`; 시장 지표는 `MARKET_DATA_READ`가 없으면 FastAPI가 `valuation: null` + 사유)
  → `CompanyProfile` (§6.3)

### 3.6 관리·감사 (Senior)
- `GET|POST /api/admin/kill-switch` `{enabled, reason}` → `{killSwitchActive, reason, toggledBy, since}`
- `GET /api/admin/guardrail-events?severity=&limit=50`
- `GET /api/admin/llm/providers` · `POST /api/admin/llm/switch` `{provider}` (FastAPI 프록시, 감사 `LLM_PROVIDER_SWITCHED`)
- `GET /api/audit?type=&limit=50` · `GET /api/audit/trace/{requestUid}`
- `GET /api/agents` (FastAPI `/ai/agents` 프록시)

감사 로그 type: `USER_LOGIN`, `USER_LOGIN_FAILED`, `ANALYSIS_REQUEST_CREATED`, `ANALYSIS_EXECUTED`, `ANALYSIS_COMPLETED`,
`REPORT_EDITED`, `PUBLICATION_SUBMITTED`, `PUBLICATION_APPROVED`, `PUBLICATION_REJECTED`, `GUARDRAIL_BLOCKED`,
`KILL_SWITCH_TOGGLED`, `LLM_PROVIDER_SWITCHED`, `AGENT_EXECUTION`(FastAPI가 씀).

## 4. FastAPI AI API (`/ai`, `X-Internal-API-Key`, 선택 헤더 `X-Request-ID`·`X-User-Id`·`X-User-Scopes`)

- `GET /ai/health` → `{status, service:"gongsi-ai-server", version, llmProvider, embeddingProvider, killSwitchActive, killSwitchReason}`
- `POST /ai/analyses` → 202 `JobStatus`
  ```json
  { "requestId": 1, "userId": "analyst_001", "company": "999001", "bsnsYear": 2025, "reprtCode": "11011",
    "query": "소송 관련 변화 중심으로", "scope": ["DISCLOSURE_READ","MARKET_DATA_READ","RAG_READ"],
    "options": { "demoFaultInjection": false } }
  ```
  입력 가드레일(query) 차단 → 422 `{"detail":{"error":"GUARDRAIL_BLOCKED","detectedIssues":[...],"requestUid":"..."}}`.
  Kill Switch → 503 `{"detail":{"error":"KILL_SWITCH_ACTIVE","reason":"..."}}`.
- `GET /ai/jobs/{jobId}` → `JobStatus`
  ```ts
  JobStatus = { jobId, status:"RUNNING"|"COMPLETED"|"FAILED", progress:number(0~1), currentStep:string|null,
    result: { report: RadarReport } | { error: string } | null,
    agentExecutions: { agentId, stepOrder, status, durationMs|null, errorMessage|null, summary|null }[] }
  ```
  `currentStep`: `PLANNING` → `DISCLOSURE` → `FINANCIAL` → `REVIEW` → (`FINANCIAL` 재실행 가능) → `WRITING` → `DONE`
- `POST /ai/rag/search` `{query, scope, topK=5, minScore=0.3, trustLevels?, corpCode?, rceptNo?}` → `{items:[{chunkId, docId, title, source, publishedAt, content, score, trustLevel, sectionPath}], total}`
- `POST /ai/guardrails/input-check` · `POST /ai/guardrails/output-check` `{text, userId?, context?}` →
  `{isSafe, riskLevel:"SAFE"|"WARNING"|"BLOCKED", detectedIssues, filteredText, shouldBlock, shouldRewrite}`
- `GET /ai/llm/providers` → `{active, providers:[{name, model, status:"healthy"|"available"|"blocked"|"unreachable", type:"local"|"external"}]}` · `POST /ai/llm/switch` `{provider}`
- `GET /ai/tools` (X-User-Scopes로 필터) · `POST /ai/tools/{name}/invoke` (헤더 `X-User-Id`, `X-User-Scopes`, `X-Agent-Id`; body=인자만) · `GET /ai/tools/calls/recent`
- `GET /ai/agents` · `POST /ai/agents/{agentId}/run` `{query, scope}` · `GET /ai/agents/llm-calls/recent`
- `GET /ai/insights/{corpCode}` (X-User-Scopes에 `DISCLOSURE_READ` 필요) → `{business, governance, notes}` — 기업 상세의 문서 파생 정보. Tool Gateway `get_document_insights`를 거친다. 403·404·502(데이터 서비스 장애)
- (제거됨, §11) `/ai/companies`·`/ai/market`·`/ai/ingest` — 데이터 API는 Spring으로 옮겼다

Tool 목록(이름·scope): `get_document_insights`(DISCLOSURE_READ),
`compare_filings`(DISCLOSURE_READ), `get_financial_changes`(DISCLOSURE_READ), `get_business_metrics`(DISCLOSURE_READ),
`get_governance`(DISCLOSURE_READ), `get_lawsuits`(DISCLOSURE_READ), `get_valuation`(MARKET_DATA_READ),
`get_stock_price`(MARKET_DATA_READ), `search_disclosures`(RAG_READ), `get_publication_history`(PUBLICATION_READ, Core 조회 키).
**발행·승인 Tool은 등록하지 않는다**(호출하면 404).

## 5. Core Zone API — 리포트 발행 원장 (`core-service/`, 9100)

인증: 조회는 `X-Internal-API-Key: CORE_API_KEY`, 쓰기는 `X-System-Key: CORE_SYSTEM_KEY`(조회 키로 쓰기 호출 → 403). 모든 요청을 `core_log`에
기록(본문 대신 `params_hash`). 응답 지연·실패 시뮬레이션: `CORE_LATENCY_MS_MIN/MAX`(기본 0), `CORE_FAIL_RATE`(기본 0).

- `GET /core/health` → `{status, service:"gongsi-core-service", version, latency_ms_range, fail_rate}`
- `POST /core/publications` (시스템 키, `X-Idempotency-Key`)
  ```json
  { "reportId": 12, "corpCode": "00999001", "corpName": "샘플소재㈜", "periodLabel": "2025 사업보고서",
    "title": "...", "contentHash": "sha256hex", "submittedBy": "analyst_001", "supersedesId": null }
  ```
  → 201 `{publicationId, status:"PENDING", version, createdAt, decisionRequiredBy}` / 같은 멱등성 키 재전송 → 200 기존 건 + `"duplicate": true`
  거절(409): `DUPLICATE_PUBLICATION`(같은 corpCode·periodLabel에 PUBLISHED가 있는데 supersedesId 없음),
  `PENDING_EXISTS`(같은 reportId에 PENDING 존재), `DAILY_LIMIT_EXCEEDED`(요청자 하루 발행 요청 `PUBLICATION_DAILY_LIMIT`=20 초과),
  `INVALID_SUPERSEDES`(supersedesId가 PUBLISHED가 아니거나 회사·기간이 다름)
- `POST /core/publications/{id}/approve` (시스템 키) `{decidedBy, contentHash}` → `{publicationId, status:"PUBLISHED", decidedBy, decidedAt, publishedAt, version}`
  409: `INVALID_STATE`(PENDING 아님), `CONTENT_CHANGED`(contentHash 불일치), `SELF_APPROVAL`(decidedBy == submittedBy), `EXPIRED`
  정정 발행(supersedesId 있음)이 승인되면 이전 건은 `SUPERSEDED`로 바뀐다.
- `POST /core/publications/{id}/reject` (시스템 키) `{decidedBy, reason}` → `{publicationId, status:"REJECTED", decidedAt}`
- `GET /core/publications?corp_code=&status=&page=0` (조회 키) → `{items:[...], total}` · `GET /core/publications/{id}`
- 상태 머신: `PENDING ─approve→ PUBLISHED ─(정정 승인)→ SUPERSEDED`, `PENDING ─reject→ REJECTED`,
  `PENDING ─timeout(PUBLICATION_DECISION_TIMEOUT_SEC=86400)→ EXPIRED`(조회·쓰기 시점에 지연 적용), `FAILED`(시스템 실패)
- `version`: 같은 corpCode·periodLabel의 PUBLISHED + SUPERSEDED 개수 + 1 (정정 뒤에도 버전이 줄지 않게)
- 409 본문은 `{"error": 코드, ...세부}`이고 같은 내용을 `detail`에도 싣는다(Quant-X처럼 `detail.error`를 읽는 클라이언트 호환)
- 거절 사유 검사 순서는 고정이다. 발행 요청: 멱등성 → DAILY_LIMIT_EXCEEDED → PENDING_EXISTS → INVALID_SUPERSEDES/DUPLICATE_PUBLICATION.
  승인: EXPIRED/INVALID_STATE → SELF_APPROVAL → CONTENT_CHANGED → 승인 시점 재확인(그 사이 같은 회사·기간이 먼저 발행됐으면 409)
- 응답은 전체 `PublicationOut`(publishedAt·rejectReason 포함), 목록은 `{items, total, page, size}`(size 기본 20, 최대 100)
- 조회 키와 시스템 키가 같거나 비어 있으면 Core가 기동을 거부한다

## 6. 리포트 JSON (`RadarReport`) — `ai-server/radar/schemas.py`가 정본

기존 필드(`meta, parse, accounts, changes, tables, relations, timeline, review, metrics`)는 그대로 두고 아래를 더한다.
`docs/report.schema.json`은 `python -m radar schema`로 다시 뽑는다.

### 6.1 Agent 래퍼 필드 (Quant-X 보고서 계약)
`title: str`, `summary: str`(개요 문장), `citations: str[]`(인용 문단 ID·`market-data:종목코드`·`dart:접수번호`),
`toolCalls: {tool, args, resultSummary, agentId}[]`, `reviewPassed: bool`, `reviewIssues: str[]`, `generatedAt: str`,
`agents: {agentId, stepOrder, status, durationMs, summary}[]`. (`meta.disclaimer`는 그대로)

### 6.2 계산식·출처 (`Formula`)
```ts
Source = { kind:"재무 API"|"원문 표"|"원문 문단"|"시세"|"계산"|"업종 피어", label:string, rceptNo?:string, pid?:string, field?:string, url?:string }
FormulaInput = { name:string, value:number|null, unit:string, source?:Source, note?:string }
Formula = { id:string, label:string, expr:string, inputs:FormulaInput[], result:number|null, unit:string,
            status:"계산됨"|"계산 안 함", reason?:string, notes:string[] }
```
- `accounts[].formulas: Formula[]` — `delta`(변동액), `yoy`(증감률), `robust_z`(피어 있을 때), `materiality`(중요성 기준 대상일 때)
- 값이 없으면 0으로 바꾸지 않고 `status:"계산 안 함"` + `reason`.

### 6.3 사업 지표 (`business`, 알파인더 참고: 구조가 명확한 표만 규칙 추출 + 검산 통과분 우선)
```ts
Business = { groups: BusinessGroup[], summary:{passed:number, failed:number, unchecked:number}, note:string }
BusinessGroup = { kind:"부문 매출"|"수주"|"생산능력·가동률", title:string, unit:string|null, sectionPath:string,
  priorPid:string|null, currentPid:string|null, checks:Check[], rows:BusinessRow[], formulas:Formula[] }
BusinessRow = { label:string, status:"검산 통과"|"검산 불일치"|"검산 불가",
  values:{name:string, unit:string, prior:number|null, current:number|null, yoyPct:number|null}[], checks:Check[] }
```
검산 규칙: 부문 매출(비중 합계≈100%, 표기 비중↔계산 비중 ±0.15%p, 표 합계↔재무 API 매출 ±0.5% 아니면 warn "연결조정 차이 가능"),
수주(수주총액 = 기납품액 + 수주잔고, 잔고 합계↔본문 "수주잔고는 약 N억원"), 생산능력·가동률(단위 일치 시에만 합계, 합계↔본문 "생산능력 N톤",
가동률 0~100% 밖이면 warn, 가중평균 가동률 Formula).

### 6.4 지배구조 (`governance`, OpenDART `hyslrSttus`·`exctvSttus`·`otrCprInvstmntSttus` 형태)
```ts
Governance = { rceptNo:string, priorRceptNo:string|null,
  shareholders:{name, relation, stockKind, beginShares, beginPct, endShares, endPct, change:"신규"|"증가"|"감소"|"전량 처분"|"변동 없음", deltaPct}[],
  executives:{name, position, registered, fullTime, duty, change:"신규 선임"|"퇴임"|"직위 변경"|"유지", priorPosition|null}[],
  investments:{name, purpose, beginPct, endPct, bookValue, change:"신규"|"처분"|"지분 증가"|"지분 감소"|"변동 없음", corpCode|null}[],
  changes:{kind:"주주"|"임원"|"출자", text:string}[],
  graph:{ nodes:{id, label, kind:"company"|"shareholder"|"person"|"investee", corpCode|null}[], edges:{from, to, pct|null, label}[] },
  note:string }
```

### 6.5 시장 지표 (`valuation`, 알파인더 TTM·PER·PBR 규칙)
```ts
Valuation = { asOf:string|null, marketSource:"sample"|"data.go.kr"|null, fsDiv:"CFS"|"OFS",
  annual:{year:number, rceptNo:string}, interim:{year:number, reprtCode:string, rceptNo:string}|null,
  price:{basDt, close, listedShares, marketCap}|null, prices:{d:string, c:number}[],
  metrics: Formula[],   // id: market_cap, ttm_revenue, ttm_op, ttm_ni_owner, per_ttm, per_annual, pbr
  notes:string[] }
```
TTM = 최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적(같은 연결·별도 범위). 이익 ≤ 0이면 PER 계산 안 함.
지배주주 계정이 없으면 전체 계정으로 대체하고 input note에 "대체 계정"을 남긴다. 판단 문구(저평가 등)는 쓰지 않는다.

### 6.6 기업 목록·상세 (Spring `/api/companies`)
```ts
CompanyRow = { corpCode, corpName, stockCode, induty|null, hasFilings:boolean, revenue:number|null, opIncome:number|null,
  opMarginPct:number|null, marketCap:number|null, per:number|null, pbr:number|null, basis:string|null }
CompanyProfile = { company:{corpCode, corpName, stockCode, induty}, filings:{rceptNo, reportNm, rceptDt, reprtCode, bsnsYear, hasDocument}[],
  financials:{ fsDiv, columns:string[], rows:{account:string, values:(number|null)[], formulas:Formula[]}[] },
  valuation: Valuation|null, valuationNote: string|null, business: Business|null, governance: Governance|null, notes:string[] }
```

## 7. MariaDB 스키마 (`scripts/sql/`, DB `gongsi`)

| 파일 | 테이블 |
|---|---|
| `01_schema.sql` | `users`, `user_scopes`, `analysis_request`, `analysis_report` |
| `02_agent_schema.sql` | `agent_execution` (Quant-X와 같음, `request_id`는 analysis_request.id) |
| `03_hitl_schema.sql` | `publication_queue` |
| `04_governance_schema.sql` | `audit_log`, `guardrail_event`, `kill_switch_status`, `agent_tool_call_log` + 계정 `gongsi_audit`·`gongsi_app` 권한 |
| `05_llm_schema.sql` | `llm_invocation_log` |
| `06_rag_schema.sql` | `disclosure_document`, `disclosure_chunk` (RAG 메타. 벡터는 Chroma) |
| `seed.sql` | 사용자 3명 + scope |

`analysis_request`: id, user_id, company, corp_code, corp_name, bsns_year INT, reprt_code VARCHAR(8), query TEXT NULL, scope_json JSON,
demo_fault_injection BOOLEAN, status, job_id, request_uid, created_at/updated_at/started_at/finished_at.
`analysis_report`: id, request_id(FK, UNIQUE), title, summary TEXT, body_json LONGTEXT(JSON), disclaimer TEXT, approval_status VARCHAR(16) DEFAULT 'DRAFT',
publication_id VARCHAR(64) NULL, content_hash VARCHAR(64) NULL, created_at, updated_at.
`publication_queue`: id, publication_id UNIQUE, report_id, idempotency_key UNIQUE, corp_code, corp_name, period_label, title, content_hash,
version INT, supersedes_id NULL, submitted_by, status, decided_by, decided_at, comment TEXT, decision_required_by, created_at, updated_at.
나머지(감사·가드레일·Kill Switch·tool·llm 로그)는 Quant-X `scripts/sql/05·06`과 같은 컬럼, DB·계정 이름만 `gongsi`로.

## 8. 로컬 실행 순서

1. `scripts/db.sh up` → Docker `gongsi-mariadb`(3307) + SQL 적용
2. (폐쇄망 모드) `ollama serve`
3. `core-service/`: `.venv/bin/uvicorn app.main:app --port 9100`
4. `ai-server/`: `.venv/bin/uvicorn app.main:app --port 8100`
5. `backend/`: `./gradlew bootRun` (8180)
6. `frontend/`: `npm run dev` → http://localhost:3100
`scripts/dev.sh`가 3~6을 백그라운드로 띄우고 로그를 `.tmp/logs/`에 남긴다.

## 9. 시장 화면 (알파인더 `/market` 참고)

- Spring: `GET /api/market?market=ALL|KOSPI|KOSDAQ|KONEX` (`MARKET_DATA_READ`) → `MarketOverview` (FastAPI 프록시)
- FastAPI: `GET /ai/market?market=` → Tool Gateway `get_market_overview`(MARKET_DATA_READ)
- 시장 필터는 시가총액 추이·업종 지도·최근 정기보고서에 적용된다. 지수 추이는 필터와 무관하다.

```ts
MarketOverview = {
  asOf: string | null,                         // 최신 시세 기준일 YYYY-MM-DD
  market: "ALL" | "KOSPI" | "KOSDAQ" | "KONEX",
  markets: { code: "ALL"|"KOSPI"|"KOSDAQ"|"KONEX", label: string, count: number }[],   // 필터 칩(전체 포함)
  universeNote: string,                        // 예: "추적 기업 44개사(가상 샘플)"
  sample: boolean,
  capitalization: {
    total: number | null,                      // 원
    series: { d: string, v: number }[],        // 일별 합계(원), 오래된 날짜 → 최신
    changes: PeriodChange[],                   // 전일·1주·1개월·1년
    availableRanges: ("1Y"|"3Y"|"5Y")[],       // 데이터가 있는 기간만. 나머지 버튼은 비활성 + 사유
    rangeNote: string | null,                  // 예: "샘플 시세는 1년치입니다"
    source: Source
  },
  indices: {
    code: "KOSPI" | "KOSDAQ", name: string,
    kind: "official" | "proxy",                // proxy: 공식 지수 키가 없어 추적 기업 시가총액으로 만든 대체 지수
    last: number | null, asOf: string | null,
    series: { d: string, v: number }[], changes: PeriodChange[],
    availableRanges: ("1Y"|"3Y"|"5Y")[], note: string, source: Source
  }[],
  sectors: SectorNode,                         // 트리맵 루트
  recentFilings: { rceptNo, rceptDt, corpCode, corpName, stockCode, reportNm, reprtCode: string|null,
                   bsnsYear: number|null, marketCap: number|null, isCorrection: boolean,
                   hasDocument: boolean, url: string }[],      // 접수일 내림차순, 최대 30건
  notes: string[]
}
PeriodChange = { period: "1D"|"1W"|"1M"|"1Y", label: "전일"|"1주"|"1개월"|"1년",
                 pct: number | null, delta: number | null, from: string | null, to: string | null, reason?: string }
SectorNode = { id: string, name: string, level: "root"|"section"|"division"|"company",
               code: string | null,                // KSIC 대분류 문자(C) · 중분류 2자리(20) · 회사는 종목코드
               value: number, count: number,       // value = 시가총액(원), count = 기업 수
               share: number,                      // 부모 대비 비중 %
               corpCode?: string, children?: SectorNode[] }
```
- 지수 `delta`는 포인트, 시가총액 `delta`는 원. 기간 기준일은 `to`(최신)에서 거꾸로 7일·1개월·1년 이내 마지막 거래일이며, 그만큼 데이터가 없으면 `pct: null` + `reason`.
- 트리맵 면적 = 시가총액, 색은 등락률을 나타내지 않는다(대분류 구분색). 업종은 KSIC(한국표준산업분류) 대분류 → 중분류 → 기업.

## 10. 일일 수집(#3)

- 적재 테이블: `scripts/sql/07_ingest_schema.sql`(`ingest_company`·`ingest_filing`·`ingest_financial_line`·`ingest_market_daily`·`ingest_index_daily`·`ingest_run`). 쓰기는 수집 전용 계정 `gongsi_ingest`(SELECT·INSERT·UPDATE, DELETE 없음), 앱 계정은 읽기만.
- 수집은 요청을 받는 서버가 아니라 예약 작업이 돌린다. 원천 API 키와 적재 쓰기 권한을 서버에 두지 않는다.
- `MarketOverview`에 추가: `newListings: {corpCode, corpName, stockCode, market, firstSeen, marketCap}[]`, `newListingsNote: string`, `ingested: boolean`.
  첫 적재일에 들어온 회사는 신규가 아니다(확인일 ≠ 공식 상장일).
- 관리: Spring `GET /api/admin/ingest`(Senior) → 수집 상태 `{enabled, reason, budget, callsToday, budgetLeft, lastMarketDate, tables, lastRun, runs[], steps[]}`. 조회만 있고 수집 시작 API는 없다.
- 감사: 실행마다 `audit_log`에 `INGEST_RUN`(단계별 상태·호출 수·행 수, 키·본문 없음).

## 11. 역할 분리 — Spring(데이터·업무) / FastAPI(AI·문서 분석)

### 11.1 경계

| | Spring (backend, 8180) | FastAPI (ai-server, 8100) |
|---|---|---|
| 원천 연동 | OpenDART·공공데이터포털 클라이언트, **원천 API 키는 여기만** | 없음(키 없음). 데이터는 Spring 내부 API로만 받는다 |
| 일일 수집(#3) | `@Scheduled` 예약 작업 + 1회 실행 모드, 수집 전용 DataSource(`gongsi_ingest`) | 없음(Python `radar/ingest`는 제거) |
| 화면 데이터 API | `/api/companies`, `/api/companies/{corpCode}`, `/api/market`, `/api/admin/ingest` — **Java로 직접 계산**(적재 DB 우선, 없으면 원천) | 없음(`/ai/companies`·`/ai/market`·`/ai/ingest` 제거) |
| 문서 분석 | — | 공시 원문 파싱·비교·관련 서술·검증·사업 지표·지배구조 변동(리포트), 에이전트·RAG·가드레일·LLM |
| 기업 상세의 문서 파생 정보 | `/api/companies/{corpCode}`가 AI `GET /ai/insights/{corpCode}`를 불러 `business`·`governance`만 붙인다 | `GET /ai/insights/{corpCode}` → `{business, governance, notes}` |

- 화면 경로·응답 모양은 바꾸지 않는다(§3.5, §6.6, §9, §10). Java 결과는 `backend/src/test/resources/golden/*.json`(분리 전 Python 결과)과 같아야 한다.
- 샘플 데이터는 저장소 루트 `samples/data/`를 두 서버가 함께 읽는다(`gongsi.data.sample-dir`, `RADAR_SAMPLE_DIR`).
- 데이터 모드: `gongsi.data.source=sample|opendart`(Spring). AI 서버는 항상 `RADAR_SOURCE=service`(Spring 내부 API). 테스트·CLI 단독 실행만 `sample`.

### 11.2 내부 데이터 API (Spring → AI 서버 전용)

- 경로 `/internal/data/**`, 헤더 `X-Internal-API-Key: DATA_API_KEY`(기본 `dev-data-internal-key`, AI 서버 키와 다른 값). JWT를 쓰지 않는다.
  프런트 프록시는 `/api`만 넘기므로 브라우저에서는 닿지 않는다. 호출마다 `X-Request-ID`·`X-User-Id`를 받으면 로그에 남긴다.
- 모든 응답에 헤더 `X-Data-Origin: sample|opendart`를 싣는다. AI 서버는 이 값으로 리포트의 `meta.sample_data`와 시장 지표 출처(`marketSource`)를 정한다 — 가상 샘플이 실제 공시처럼 보이면 안 된다.
- **응답 모양은 원천 그대로**(OpenDART·공공데이터포털 필드) — radar 파이프라인 코드가 바뀌지 않게. 없으면 404 `{"detail": "..."}`(radar는 `SourceError`로 받는다).

| 메서드·경로 | 응답 |
|---|---|
| `GET /internal/data/companies/resolve?q=` | `{corp_code, corp_name, stock_code, induty, induty_code, market}` (종목코드·고유번호·회사명) |
| `GET /internal/data/companies` | 위 모양의 배열(상장사) |
| `GET /internal/data/filings?corpCode=` | `[{rcept_no, report_nm, rcept_dt, reprt_code, bsns_year, hasDocument}]` 최신순 |
| `GET /internal/data/report?corpCode=&bsnsYear=&reprtCode=` | `find_report` 모양 `{corp_code, corp_name, stock_code, report_nm, rcept_no, rcept_dt, rm, bsns_year, reprt_code, url, is_correction}` |
| `GET /internal/data/documents/{rceptNo}` | `application/zip` 원문(document.xml ZIP 바이트) |
| `GET /internal/data/financials?corpCode=&bsnsYear=&reprtCode=` | `{fs_div, list:[fnlttSinglAcntAll 행]}` (CFS 없으면 OFS) |
| `GET /internal/data/peers?corpCode=&bsnsYear=&reprtCode=` | `{list:[fnlttMultiAcnt 행]}` |
| `GET /internal/data/lawsuits?corpCode=&bgn=&end=` | `{list:[lwstLg 행]}` |
| `GET /internal/data/governance?corpCode=&bsnsYear=&reprtCode=` | `{shareholders, executives, investments, rcept_no}` (hyslrSttus·exctvSttus·otrCprInvstmntSttus 행) |
| `GET /internal/data/market/{stockCode}` | `{items:[getStockPriceInfo 행]}` 최신순 |
