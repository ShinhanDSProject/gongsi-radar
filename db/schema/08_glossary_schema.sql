-- 용어집(#14). 화면 툴팁과 용어집 페이지의 정본. 사람이 검토·승인한 것만 게시한다.
-- 상태: DRAFT(작성 중) → PENDING(검토 대기) → PUBLISHED(게시) / REJECTED(반려, 고쳐서 다시 요청)
-- 게시된 정의도 출력 필터(투자 권유·가치판단 표현)를 통과해야 한다. 삭제하지 않고 게시 취소(DRAFT로)만 한다.
USE gongsi;
CREATE TABLE IF NOT EXISTS glossary_term (
  id              BIGINT PRIMARY KEY AUTO_INCREMENT,
  term            VARCHAR(100) NOT NULL UNIQUE,            -- 표제어(화면에서 찾는 말)
  aliases         VARCHAR(500),                            -- 같은 뜻으로 찾을 말, 쉼표 구분(예: '최근 12개월')
  definition      TEXT         NOT NULL,                   -- 쉬운 정의 2~3문장
  usage_note      VARCHAR(500),                            -- 공시레이더에서 쓰이는 곳
  related         VARCHAR(300),                            -- 관련 용어, 쉼표 구분
  source          VARCHAR(300),                            -- 근거(법령·OpenDART 가이드·회계기준 등)
  status          VARCHAR(16)  NOT NULL DEFAULT 'DRAFT',   -- DRAFT, PENDING, PUBLISHED, REJECTED
  ai_drafted      BOOLEAN      NOT NULL DEFAULT FALSE,     -- 정의 초안을 LLM이 썼는가(게시 전 사람 검토 필수)
  created_by      VARCHAR(64)  NOT NULL,
  submitted_by    VARCHAR(64),
  reviewed_by     VARCHAR(64),
  reviewed_at     DATETIME(6),
  review_comment  VARCHAR(500),
  created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_gt_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 앱 계정: 읽기·쓰기(삭제 없음 — 게시 취소는 상태 변경)
GRANT SELECT, INSERT, UPDATE ON gongsi.glossary_term TO 'gongsi_app'@'%';
