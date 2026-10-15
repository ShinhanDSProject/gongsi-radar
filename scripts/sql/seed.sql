-- 더미 사용자 3명(비밀번호 모두 'password', BCrypt) + Scope. 멱등.
USE gongsi;
INSERT INTO users (user_id, password_hash, name, email, role, active) VALUES
  ('analyst_001', '$2a$10$ScFGZ9H9R8ZIf9C10khMs.oKGihNwNxtiRN.X.5hkDF/Gr6ZTVJh6', '주니어 김', 'jr1@example.com', 'JUNIOR_ANALYST', TRUE),
  ('analyst_002', '$2a$10$ScFGZ9H9R8ZIf9C10khMs.oKGihNwNxtiRN.X.5hkDF/Gr6ZTVJh6', '주니어 박', 'jr2@example.com', 'JUNIOR_ANALYST', TRUE),
  ('senior_001',  '$2a$10$ScFGZ9H9R8ZIf9C10khMs.oKGihNwNxtiRN.X.5hkDF/Gr6ZTVJh6', '시니어 이', 'sr@example.com',  'SENIOR_MANAGER', TRUE)
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), name = VALUES(name), email = VALUES(email),
  role = VALUES(role), active = VALUES(active);

INSERT IGNORE INTO user_scopes (user_id, scope, granted_at)
SELECT u.id, s.scope, NOW(6) FROM users u
JOIN (SELECT 'DISCLOSURE_READ' AS scope UNION ALL SELECT 'MARKET_DATA_READ' UNION ALL SELECT 'RAG_READ' UNION ALL SELECT 'REPORT_READ') s
WHERE u.user_id IN ('analyst_001', 'analyst_002', 'senior_001');

INSERT IGNORE INTO user_scopes (user_id, scope, granted_at)
SELECT u.id, s.scope, NOW(6) FROM users u
JOIN (SELECT 'REPORT_WRITE' AS scope UNION ALL SELECT 'PUBLICATION_READ') s
WHERE u.user_id = 'senior_001';
