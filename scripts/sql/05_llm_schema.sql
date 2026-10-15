-- 10장 대응: LLM 호출 기록. 프롬프트 전문 대신 해시만 남긴다.
USE gongsi;
CREATE TABLE IF NOT EXISTS llm_invocation_log (
  id                BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_uid       VARCHAR(64),
  execution_id      BIGINT,
  agent_id          VARCHAR(64),
  provider          VARCHAR(32)  NOT NULL,          -- openai, ollama, mock
  model_name        VARCHAR(128) NOT NULL,
  prompt_hash       VARCHAR(64),
  prompt_chars      INT,
  prompt_tokens     INT,
  completion_tokens INT,
  duration_ms       INT,
  status            VARCHAR(16)  NOT NULL,          -- SUCCESS, FAIL
  error_message     TEXT,
  created_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_lil_request_uid (request_uid),
  INDEX idx_lil_execution (execution_id),
  INDEX idx_lil_provider (provider, model_name),
  INDEX idx_lil_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
GRANT INSERT, SELECT ON gongsi.llm_invocation_log TO 'gongsi_audit'@'%';
GRANT SELECT          ON gongsi.llm_invocation_log TO 'gongsi_app'@'%';
FLUSH PRIVILEGES;
