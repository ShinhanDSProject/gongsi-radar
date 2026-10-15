-- 8장 대응: 리포트 발행 결재 큐. Core Zone(발행 원장)과 상태를 동기화한다.
-- 멱등성 키는 Core 호출 전에 여기 먼저 저장한다 — 재시도 때 같은 키를 다시 쓰기 위해
USE gongsi;
CREATE TABLE IF NOT EXISTS publication_queue (
  id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
  publication_id        VARCHAR(64)  UNIQUE,              -- Core Zone이 준 ID(접수 성공 후 채움)
  report_id             BIGINT       NOT NULL,
  idempotency_key       VARCHAR(64)  NOT NULL UNIQUE,
  corp_code             VARCHAR(16)  NOT NULL,
  corp_name             VARCHAR(100) NOT NULL,
  period_label          VARCHAR(64)  NOT NULL,            -- '2025 사업보고서'
  title                 VARCHAR(500) NOT NULL,
  content_hash          VARCHAR(64)  NOT NULL,            -- 발행 요청 시점 body_json의 SHA-256
  version               INT,
  supersedes_id         VARCHAR(64),
  submitted_by          VARCHAR(64)  NOT NULL,
  status                VARCHAR(16)  NOT NULL,            -- SUBMITTING, PENDING, PUBLISHED, REJECTED, EXPIRED, FAILED, SUPERSEDED
  decided_by            VARCHAR(64),
  decided_at            DATETIME(6),
  comment               TEXT,
  decision_required_by  DATETIME(6),
  created_at            DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at            DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_pq_status (status),
  INDEX idx_pq_report (report_id),
  INDEX idx_pq_corp (corp_code),
  INDEX idx_pq_submitted_by (submitted_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
