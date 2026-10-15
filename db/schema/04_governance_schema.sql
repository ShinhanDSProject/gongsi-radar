-- 9장 대응: 감사 3종 · Kill Switch · 계정 분리
-- 감사 테이블은 append-only. 트리거가 아니라 전용 계정 권한으로 막는다(Quant-X 9장과 같은 판단).
USE gongsi;
CREATE TABLE IF NOT EXISTS audit_log (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  type             VARCHAR(64)  NOT NULL,
  request_uid      VARCHAR(64),
  user_id          VARCHAR(64),
  agent_id         VARCHAR(64),
  request_id       BIGINT,
  payload_json     JSON         NOT NULL,          -- 요약만. 원문·PII는 넣지 않는다
  payload_hash     VARCHAR(64),                    -- SHA-256(payload_json)
  prev_hash        VARCHAR(64),                    -- 직전 레코드 payload_hash(해시 체인)
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_al_type (type),
  INDEX idx_al_user (user_id),
  INDEX idx_al_uid (request_uid),
  INDEX idx_al_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS guardrail_event (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  type             VARCHAR(32)  NOT NULL,          -- INPUT, OUTPUT, CONTEXT
  severity         VARCHAR(16)  NOT NULL,          -- SAFE, WARNING, BLOCKED
  request_uid      VARCHAR(64),
  user_id          VARCHAR(64),
  agent_id         VARCHAR(64),
  request_id       BIGINT,
  detected_issues  JSON         NOT NULL,
  payload_hash     VARCHAR(64)  NOT NULL,          -- 원문 SHA-256. 원문은 저장하지 않는다
  filtered_text    TEXT,                           -- 마스킹을 마친 결과
  blocked          BOOLEAN      NOT NULL,
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_ge_severity (severity),
  INDEX idx_ge_user (user_id),
  INDEX idx_ge_uid (request_uid),
  INDEX idx_ge_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kill_switch_status (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  active           BOOLEAN      NOT NULL,
  reason           VARCHAR(500),
  toggled_by       VARCHAR(64)  NOT NULL,
  toggled_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_ks_toggled (toggled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO kill_switch_status (active, reason, toggled_by)
SELECT 0, '초기 상태', 'system' WHERE NOT EXISTS (SELECT 1 FROM kill_switch_status);

CREATE TABLE IF NOT EXISTS agent_tool_call_log (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_uid      VARCHAR(64),
  execution_id     BIGINT,
  agent_id         VARCHAR(64)  NOT NULL,
  user_id          VARCHAR(64)  NOT NULL,
  tool_name        VARCHAR(128) NOT NULL,
  scope_json       JSON         NOT NULL,
  scope_pass       BOOLEAN      NOT NULL,
  params_hash      VARCHAR(64),
  result_summary   TEXT,
  duration_ms      INT,
  error_message    TEXT,
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_atc_agent (agent_id),
  INDEX idx_atc_tool (tool_name),
  INDEX idx_atc_user (user_id),
  INDEX idx_atc_uid (request_uid),
  INDEX idx_atc_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE USER IF NOT EXISTS 'gongsi_audit'@'%' IDENTIFIED BY 'audit-only-pass';
GRANT INSERT, SELECT ON gongsi.audit_log           TO 'gongsi_audit'@'%';
GRANT INSERT, SELECT ON gongsi.guardrail_event     TO 'gongsi_audit'@'%';
GRANT INSERT, SELECT ON gongsi.agent_tool_call_log TO 'gongsi_audit'@'%';

CREATE USER IF NOT EXISTS 'gongsi_app'@'%' IDENTIFIED BY 'app-pass';
GRANT SELECT                 ON gongsi.users              TO 'gongsi_app'@'%';
GRANT SELECT                 ON gongsi.user_scopes        TO 'gongsi_app'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.analysis_request   TO 'gongsi_app'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.analysis_report    TO 'gongsi_app'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.agent_execution    TO 'gongsi_app'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.publication_queue  TO 'gongsi_app'@'%';
GRANT SELECT, INSERT         ON gongsi.kill_switch_status TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.audit_log           TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.guardrail_event     TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.agent_tool_call_log TO 'gongsi_app'@'%';
FLUSH PRIVILEGES;
