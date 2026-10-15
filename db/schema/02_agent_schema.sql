-- 7장 대응: Worker 실행 이력. FK를 두지 않는다(두 서버가 다른 시점에 기록 — Quant-X와 같은 판단)
USE gongsi;
CREATE TABLE IF NOT EXISTS agent_execution (
  id                BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_id        BIGINT       NOT NULL,          -- analysis_request.id
  job_id            VARCHAR(64)  NOT NULL,
  agent_id          VARCHAR(64)  NOT NULL,
  step_order        INT          NOT NULL,
  status            VARCHAR(32)  NOT NULL,          -- RUNNING, COMPLETED, FAILED
  input_text        MEDIUMTEXT,
  output_text       MEDIUMTEXT,
  model_provider    VARCHAR(32),
  model_name        VARCHAR(128),
  duration_ms       INT,
  error_message     TEXT,
  started_at        DATETIME(6),
  finished_at       DATETIME(6),
  created_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_ae_job (job_id),
  INDEX idx_ae_agent (agent_id),
  INDEX idx_ae_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
