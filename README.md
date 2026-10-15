# 공시레이더 프로토타입

DART 정기보고서 두 건(전년 같은 보고서와 당기 보고서)을 비교해 **바뀐 문단**을 찾고, 수치 변화가 큰 계정마다
**회사가 공시 본문에서 밝힌 서술**을 원문 인용과 함께 연결한 뒤, **코드 검증 → 사람 검토(결재) → 공유**로 넘기는
파이프라인과 리뷰 화면입니다. 사업계획서 v2의 Must 기능을 끝까지 연결한 동작 버전입니다.

> 샘플 데이터의 회사(샘플소재㈜)·인물·수치는 모두 **가상**입니다. 원문 XML에는 실제 DART 원문에서 알려진 함정
> (감사보고서 동봉, 이스케이프 안 된 `&`, TE/TU 셀, cp949인데 utf-8 선언, 가짜 태그)과 레드팀용 인젝션 문단을 일부러 넣었습니다.

## 빠른 시작

**Python 3.10 이상**이 필요합니다(`str | None` 같은 타입 문법을 씀). macOS 기본 `python3`는 3.9라서 실행되지 않으니,
Homebrew 등으로 설치한 3.10+ 버전으로 가상환경을 만드세요.

```bash
python3.12 -m venv .venv            # 3.10 이상이면 어느 버전이든 됨
source .venv/bin/activate
pip install -r requirements.txt
python -m radar demo --fault        # 샘플 분석 → out/report.json, out/report.html (브라우저로 바로 열림)
python -m radar serve --port 8000   # API + 리뷰 화면 → http://127.0.0.1:8000/
python -m unittest -v               # 테스트 36개
```

`--fault`는 시연용 옵션입니다. 첫 시도에서 영업이익 증감률을 일부러 틀리게 써서, 검증이 반려하고 관련 서술 연결을
다시 돌려 통과하는 루프를 보여 줍니다(리포트에 "시연용 오류 주입"으로 표시).

## 실데이터(OpenDART)로 실행

```bash
export RADAR_SOURCE=opendart OPENDART_API_KEY=발급받은키      # 키는 서버 환경변수 1개로만 관리(약관 제19조②)
python -m radar run --company 005930 --year 2025 --reprt 11012   # 2025 반기 vs 2024 반기
```

- 응답은 `.cache/opendart/`에 캐시합니다. 원문 ZIP은 `rcept_no`로 영구 캐시하므로 같은 비교를 다시 돌려도 호출이 늘지 않습니다.
- 업종 피어(robust z)를 쓰려면 피어 고유번호 목록 JSON을 `RADAR_PEERS_FILE`로 지정합니다(다중회사 주요계정 API, 100개사씩).
- 12월 결산 법인만 지원합니다. 은행·보험·증권은 손익 구조가 달라 결과를 신뢰하기 어렵습니다.

### W1 파싱 스파이크

```bash
python -m radar parse 다운받은원문.zip --rcept-no 20250311001085 --blocks
```
본문 파일 선택, 인코딩, `&` 수리 건수, TE/TU 셀 수, 섹션별 문단·표 수를 출력합니다. 시연 후보 기업을 여기에 돌려 보고
10/21 관문에서 종목과 주 데모 보고서를 정하세요.

## LLM·임베딩 켜기

| 설정 | 효과 |
|---|---|
| (기본) | 규칙 모드. 외부 호출 없음, 결과가 결정적이라 테스트·시연에 씀 |
| `OPENAI_API_KEY=...` | OpenAI Structured Outputs(strict)로 변경 요약·관련 서술 판정·2단 판정·재작성. 실패 시 1~2회 재시도 후 규칙으로 폴백 |
| `RADAR_LLM=on RADAR_LLM_BASE_URL=http://localhost:11434/v1` | Ollama 등 OpenAI 호환 서버 |
| `RADAR_LLM_SMALL`, `RADAR_LLM_LARGE` | 모델 이름(기본 gpt-4o-mini / gpt-4o) |
| `RADAR_EMBEDDER=kure` | KURE-v1 임베딩(`pip install sentence-transformers`, 최초 실행 시 모델 다운로드). `qwen3`은 비교 실험용 |
| `RADAR_GRAPH=builtin` | LangGraph 대신 같은 토폴로지의 내장 러너 |

LLM을 켜도 **숫자는 코드가 계산하고, LLM이 쓴 문장은 규칙 모드와 똑같은 검증을 통과해야** 리포트에 남습니다.

## 파이프라인 (고정 DAG)

```
수집·파싱 → 수치 분석 → 본문 비교 → 관련 서술 연결 → 검증 ─통과→ Report Writer
                                         ↑               │
                                         └─반려(최대 2회)─┘
```

| 단계 | 모듈 | 하는 일 |
|---|---|---|
| 수집·파싱 | `sources.py`, `parser.py` | OpenDART/샘플에서 목록·원문·재무·피어·소송 공시를 받고 원문을 섹션·문단·표로 나눔. 문단 ID = `{rcept_no}:{섹션 키}:{해시 8자리}` |
| 수치 분석 | `financials.py` | 당기 보고서 한 건 안의 당기·전기 값으로 증감 계산. 업종 내 robust z(\|z\|>3) + 중요성(변동액 ≥ 매출 1%, 증감률 ≥ 30%) 플래그 |
| 본문 비교 | `align.py`, `tables.py`, `classify.py` | 숫자 마스킹 → 임베딩 → 순서 보존 정렬 → 분할·병합·이동·같은 자리 판정 → 신설/삭제/수치 수정/표현 수정. 기준연도만 바뀐 문단은 제외. 표는 행 단위 규칙 diff. 주제 분류·요약, 인젝션 의심 탐지, 중복(II-5와 주석) 제거 |
| 관련 서술 연결 | `relate.py` | 계정마다 대상 섹션(II·III-3·IV·X·XI)에서 근거를 찾아 **인과 명시 / 관련 맥락 / 확인 불가**로 판정, 원인 구절을 원문에서 그대로 인용 |
| 검증 | `verify.py` | 1단(코드): 인용 ID 존재, 금액·증감률 재계산, 증감 방향, 근거 수준 재확인, 본문 수치 대조, 주요사항보고서(소송) 교차 확인. 2단: 지지/불충분/모순. 출력 필터 → 재작성 → 다시 검증 |
| Report Writer | `graph.py`, `schemas.py` | `docs/report.schema.json` 계약에 맞는 리포트 JSON |

## API (AI Layer)

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/analyses` | 분석 시작(202, 비동기 Job). 본문 `{company, bsns_year, reprt_code, demo_fault_injection}`, 헤더 `X-Request-UID` |
| GET | `/api/analyses` | 지난 분석 목록 |
| GET | `/api/analyses/{id}` | 상태와 단계별 진행 이벤트(폴링용) |
| GET | `/api/analyses/{id}/report` | 리포트 JSON |
| POST | `/api/analyses/{id}/review` | 검토: `{reviewer, action: edit\|approve\|request_changes, comment, edits:[{item_id, value}]}`. 수정 문구도 출력 필터 통과 필수, 승인 후 잠금(409) |
| GET | `/api/analyses/{id}/audit` | 감사 로그(append-only JSONL) |
| GET/POST | `/api/admin/kill-switch` | 켜면 새 분석과 승인이 막힘(423) |

`RADAR_INTERNAL_KEY`를 설정하면 모든 API가 `X-Internal-Key` 헤더를 요구합니다(Spring → FastAPI 내부 키).
실제 구조에서는 인증·HITL·감사 로그를 Spring Boot가 맡고, 이 서버의 review/audit/kill-switch는 단독 시연용입니다.

## 리뷰 화면 (`web/`)

React 18 + esbuild, 단일 HTML. `cd web && npm install && node build.mjs`로 `web/dist/`를 다시 만듭니다.
- 서버에서 열면(`/`) 새 분석·진행 상황·지난 분석 목록이 보이고, 결재(승인·수정 요청·항목 수정)가 API로 기록됩니다.
- `out/report.html`처럼 리포트가 심긴 파일은 서버 없이 열리고, 결재는 그 브라우저 화면에만 반영됩니다.
- React는 cdnjs에서, 글꼴은 Google Fonts에서 불러오므로 인터넷 연결이 필요합니다.

## 이 프로토타입에서 확인한 것과 못 한 것

확인함: 파서(함정 5종), 문단 정렬·변경 유형, 수치·플래그, 3단계 근거 수준, 1·2단 검증과 반려 루프, 출력 필터·재작성·재검증,
인젝션 탐지, 리뷰·감사 로그·Kill Switch(Starlette 서버로 HTTP 왕복), 리뷰 화면(데스크톱·모바일·다크 렌더).

이 개발 환경에서는 패키지 설치와 외부 API가 막혀 있어 **직접 실행하지 못한 경로**가 있습니다. 팀 환경에서 먼저 확인하세요.
- `radar/api.py`(FastAPI): 같은 경로·같은 서비스 계층을 쓰는 Starlette 대체 서버(`devserver.py`)로 검증함
- LangGraph `StateGraph` 경로: 같은 노드·같은 간선의 내장 러너로 검증함
- OpenDART 실호출(`OpenDartSource`), OpenAI 호출(가짜 응답으로 재시도·폴백만 테스트), KURE-v1 임베딩

임계값(`config.ALIGN_THRESHOLDS`)은 샘플 기준 초기값입니다. 평가 계획대로 dev셋 4개사로만 조정하세요.
