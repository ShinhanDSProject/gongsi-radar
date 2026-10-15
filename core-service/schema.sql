-- Core Zone — 리포트 발행 원장 스키마 (SQLite). docs/CONTRACT.md §5와 같은 내용이다.
-- 서비스가 뜰 때 db.py가 이 파일을 그대로 실행한다.
-- Quant-X mock-core-service의 mock_orders 자리에 publications가 들어간다.

CREATE TABLE IF NOT EXISTS publications (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  publication_id        TEXT NOT NULL UNIQUE,             -- UUID
  idempotency_key       TEXT NOT NULL UNIQUE,             -- 중복 접수 차단
  report_id             INTEGER NOT NULL,                 -- Spring analysis_report.id
  corp_code             TEXT NOT NULL,                    -- DART 고유번호 8자리
  corp_name             TEXT NOT NULL,
  period_label          TEXT NOT NULL,                    -- '2025 사업보고서'
  title                 TEXT NOT NULL,
  content_hash          TEXT NOT NULL,                    -- SHA-256(body_json 정규화). 승인 시 다시 대조한다
  version               INTEGER NOT NULL,                 -- 같은 회사·기간의 발행 순번
  supersedes_id         TEXT,                             -- 정정 발행이면 이전 publication_id
  status                TEXT NOT NULL CHECK(status IN
                          ('PENDING','PUBLISHED','REJECTED','EXPIRED','FAILED','SUPERSEDED')),
  submitted_by          TEXT NOT NULL,                    -- 발행 요청자 user_id
  decided_by            TEXT,                             -- 승인·반려자 user_id
  decided_at            TEXT,
  published_at          TEXT,
  reject_reason         TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  decision_required_by  TEXT NOT NULL,                    -- 만료 시각

  FOREIGN KEY (supersedes_id) REFERENCES publications(publication_id)
);

CREATE INDEX IF NOT EXISTS idx_pub_corp_period ON publications(corp_code, period_label);
CREATE INDEX IF NOT EXISTS idx_pub_report      ON publications(report_id);
CREATE INDEX IF NOT EXISTS idx_pub_status      ON publications(status);
CREATE INDEX IF NOT EXISTS idx_pub_submitter   ON publications(submitted_by, created_at);

-- Core가 자기 앞으로 들어온 호출을 직접 남기는 감사 로그.
-- Spring·AI 서버의 감사 로그와 별개다. Core Zone은 자기 기록을 스스로 갖는다.
CREATE TABLE IF NOT EXISTS core_log (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id        TEXT NOT NULL,                        -- correlation ID
  caller            TEXT NOT NULL,                        -- 'ai-server' | 'spring-boot'
  caller_user_id    TEXT,
  endpoint          TEXT NOT NULL,
  method            TEXT NOT NULL,
  params_hash       TEXT,                                 -- SHA-256 (본문은 남기지 않는다)
  status_code       INTEGER NOT NULL,
  duration_ms       INTEGER NOT NULL,
  error             TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cl_caller   ON core_log(caller);
CREATE INDEX IF NOT EXISTS idx_cl_endpoint ON core_log(endpoint);
CREATE INDEX IF NOT EXISTS idx_cl_created  ON core_log(created_at);
