-- 3장 대응: 사용자·권한·분석 요청·리포트
-- 관리자(root) 계정으로 적용한다. 멱등(CREATE TABLE IF NOT EXISTS).
CREATE DATABASE IF NOT EXISTS gongsi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gongsi;

CREATE TABLE IF NOT EXISTS users (
  id              BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id         VARCHAR(64)  NOT NULL UNIQUE,
  password_hash   VARCHAR(255) NOT NULL,
  name            VARCHAR(100) NOT NULL,
  email           VARCHAR(255),
  role            VARCHAR(32)  NOT NULL,          -- JUNIOR_ANALYST, SENIOR_MANAGER, ADMIN
  active          BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_scopes (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id     BIGINT NOT NULL,
  scope       VARCHAR(64) NOT NULL,               -- DISCLOSURE_READ, MARKET_DATA_READ, RAG_READ, REPORT_READ, REPORT_WRITE, PUBLICATION_READ
  granted_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  expires_at  DATETIME(6),
  CONSTRAINT fk_user_scopes_user FOREIGN KEY (user_id) REFERENCES users(id),
  UNIQUE KEY uk_user_scopes (user_id, scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analysis_request (
  id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id               VARCHAR(64)  NOT NULL,
  company               VARCHAR(100) NOT NULL,      -- 사용자가 입력한 값(종목코드·고유번호·회사명)
  corp_code             VARCHAR(16),                -- AI 서버가 확정한 고유번호(완료 후 채움)
  corp_name             VARCHAR(100),
  bsns_year             INT          NOT NULL,
  reprt_code            VARCHAR(8)   NOT NULL,      -- 11011 사업 · 11012 반기 · 11013 1분기 · 11014 3분기
  query                 TEXT,                       -- 선택: 관심 질문(입력 가드레일 대상)
  scope_json            JSON,
  demo_fault_injection  BOOLEAN      NOT NULL DEFAULT FALSE,
  status                VARCHAR(32)  NOT NULL DEFAULT 'CREATED',   -- CREATED, RUNNING, COMPLETED, FAILED, BLOCKED
  job_id                VARCHAR(64),
  request_uid           VARCHAR(64),
  created_at            DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at            DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  started_at            DATETIME(6),
  finished_at           DATETIME(6),
  INDEX idx_ar_user (user_id),
  INDEX idx_ar_status (status),
  INDEX idx_ar_corp (corp_code),
  INDEX idx_ar_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analysis_report (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_id       BIGINT       NOT NULL UNIQUE,
  title            VARCHAR(500) NOT NULL,
  summary          TEXT,
  body_json        LONGTEXT     NOT NULL,           -- RadarReport 전체(JSON 문자열)
  disclaimer       TEXT,
  approval_status  VARCHAR(16)  NOT NULL DEFAULT 'DRAFT',   -- DRAFT, PENDING, APPROVED, REJECTED
  publication_id   VARCHAR(64),
  content_hash     VARCHAR(64),
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_report_request FOREIGN KEY (request_id) REFERENCES analysis_request(id),
  INDEX idx_report_approval (approval_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
