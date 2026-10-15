# core-service — Core Zone (리포트 발행 원장)

Quant-X `mock-core-service`(주문 원장)를 공시레이더 도메인으로 옮긴 서비스다. 리포트는 사람(Senior)이 승인해야만
이 원장에 `PUBLISHED`로 남는다. 계약은 `docs/CONTRACT.md` §5가 정본이다.

- FastAPI + SQLite(SQLAlchemy), 포트 **9100**, DB `core-service/data/core.db`(git 제외)
- 조회 `X-Internal-API-Key: CORE_API_KEY`(AI 서버), 쓰기 `X-System-Key: CORE_SYSTEM_KEY`(Spring만). 조회 키로 쓰기 → 403.
  두 키가 같으면 서비스가 뜨지 않는다.
- 모든 호출을 `core_log`에 남긴다. 본문은 남기지 않고 `params_hash`(SHA-256)만 둔다.
- `CORE_LATENCY_MS_MIN/MAX`, `CORE_FAIL_RATE`로 지연·503을 흉내낸다(기본 0).

## 실행

```bash
cd core-service
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # 필요하면 값 수정
.venv/bin/uvicorn app.main:app --port 9100
.venv/bin/pytest -q
```

## API

| 메서드 | 경로 | 키 | 설명 |
|---|---|---|---|
| GET | `/core/health` | 없음 | 상태·지연 범위·실패율 |
| POST | `/core/publications` | 시스템 + `X-Idempotency-Key` | 발행 요청 → 201 PENDING, 같은 키 재전송 → 200 + `duplicate: true` |
| POST | `/core/publications/{id}/approve` | 시스템 | `{decidedBy, contentHash}` → PUBLISHED (정정이면 이전 건 SUPERSEDED) |
| POST | `/core/publications/{id}/reject` | 시스템 | `{decidedBy, reason}` → REJECTED |
| GET | `/core/publications?corp_code=&status=&page=0&size=20` | 조회 | `{items, total, page, size}` |
| GET | `/core/publications/{id}` | 조회 | 단건 |

409 본문: `{"error": "<코드>", ...세부, "detail": {같은 내용}}`

- 접수: `DAILY_LIMIT_EXCEEDED` → `PENDING_EXISTS` → `INVALID_SUPERSEDES` / `DUPLICATE_PUBLICATION` 순서로 검사한다(사유는 항상 하나).
- 승인: `EXPIRED` / `INVALID_STATE` → `SELF_APPROVAL` → `CONTENT_CHANGED` → (승인 시점 재확인) `INVALID_SUPERSEDES` / `DUPLICATE_PUBLICATION`.
- 만료(`PUBLICATION_DECISION_TIMEOUT_SEC`, 기본 86400)는 스케줄러 없이 조회·쓰기 직전에 적용한다.
- 하루 한도(`PUBLICATION_DAILY_LIMIT`, 기본 20)는 요청자별, 한국 시간 자정 기준, 상태와 무관하게 센다.
- `version` = 같은 회사·기간의 PUBLISHED + SUPERSEDED 수 + 1.
