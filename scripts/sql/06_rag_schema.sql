-- 4장 대응: RAG 문서 메타. 벡터는 Chroma에 두고 MariaDB는 메타만 보관한다.
USE gongsi;
CREATE TABLE IF NOT EXISTS disclosure_document (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  doc_id           VARCHAR(128) NOT NULL UNIQUE,    -- dart:{rcept_no}
  corp_code        VARCHAR(16)  NOT NULL,
  rcept_no         VARCHAR(20)  NOT NULL,
  title            VARCHAR(500) NOT NULL,
  doc_type         VARCHAR(64)  NOT NULL,           -- periodic_report, major_event, external
  source           VARCHAR(255),
  published_at     DATE,
  trust_level      VARCHAR(16)  NOT NULL DEFAULT 'HIGH',   -- HIGH, MEDIUM, LOW
  content_hash     VARCHAR(64),
  meta_json        JSON,
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_dd_corp (corp_code),
  INDEX idx_dd_published (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS disclosure_chunk (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  doc_id           VARCHAR(128) NOT NULL,
  chunk_id         VARCHAR(160) NOT NULL UNIQUE,    -- 문단 인용 ID: {rcept_no}:{섹션 키}:{해시}
  chunk_index      INT          NOT NULL,
  section_path     VARCHAR(500),
  content          MEDIUMTEXT   NOT NULL,
  trust_level      VARCHAR(16)  NOT NULL DEFAULT 'HIGH',
  injection_flag   BOOLEAN      NOT NULL DEFAULT FALSE,  -- 지시문 의심 문단(검색에서 격리)
  embedding_model  VARCHAR(128),
  vector_id        VARCHAR(160),
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_dc_doc (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
GRANT SELECT, INSERT, UPDATE ON gongsi.disclosure_document TO 'gongsi_app'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.disclosure_chunk    TO 'gongsi_app'@'%';
FLUSH PRIVILEGES;
