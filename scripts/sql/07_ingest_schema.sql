-- #3 일일 수집 파이프라인: 전 종목 기업·공시·재무·시세 적재
-- 관리자(root) 계정으로 적용한다. 멱등(CREATE TABLE IF NOT EXISTS).
--
-- 쓰는 쪽은 수집 작업 전용 계정(gongsi_ingest) 하나다. 앱(gongsi_app)은 읽기만 한다.
-- 감사 테이블과 같은 사상 — 데이터를 바꿀 수 있는 경로를 하나로 좁힌다.
-- 적재 테이블은 원천(OpenDART·공공데이터포털)의 사본이다. 원천이 정본이고, 여기 값은 언제든 다시 받을 수 있다.
USE gongsi;

-- 상장사 목록(corpCode.xml + company.json). first_seen은 우리가 처음 확인한 날 — 공식 상장일과 다를 수 있다
CREATE TABLE IF NOT EXISTS ingest_company (
  corp_code      VARCHAR(16)  PRIMARY KEY,
  corp_name      VARCHAR(100) NOT NULL,
  stock_code     VARCHAR(16),
  market         VARCHAR(16),                    -- KOSPI, KOSDAQ, KONEX (시세에서 확인)
  induty_code    VARCHAR(16),                    -- KSIC (기업개황)
  induty_checked DATE,                           -- 업종 코드를 마지막으로 확인한 날
  listed         BOOLEAN      NOT NULL DEFAULT TRUE,
  first_seen     DATE         NOT NULL,
  last_seen      DATE         NOT NULL,
  updated_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_ic_stock (stock_code),
  INDEX idx_ic_first_seen (first_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 정기공시(list.json). 원문 ZIP 자체는 디스크 캐시에 두고 여기에는 보유 여부만 남긴다
CREATE TABLE IF NOT EXISTS ingest_filing (
  rcept_no        VARCHAR(20)  PRIMARY KEY,
  corp_code       VARCHAR(16)  NOT NULL,
  corp_name       VARCHAR(100),
  stock_code      VARCHAR(16),
  report_nm       VARCHAR(200) NOT NULL,
  reprt_code      VARCHAR(8),
  bsns_year       INT,
  rcept_dt        VARCHAR(8)   NOT NULL,
  rm              VARCHAR(32),
  is_correction   BOOLEAN      NOT NULL DEFAULT FALSE,
  has_document    BOOLEAN      NOT NULL DEFAULT FALSE,
  financial_done  BOOLEAN      NOT NULL DEFAULT FALSE,  -- 재무 적재를 마쳤다(다시 부르지 않는다)
  created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_if_corp (corp_code),
  INDEX idx_if_dt (rcept_dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 재무(fnlttSinglAcntAll). OpenDART 행의 금액 필드를 문자열 그대로 둔다 — 원천 표기와 대조할 수 있게
CREATE TABLE IF NOT EXISTS ingest_financial_line (
  id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
  corp_code          VARCHAR(16)  NOT NULL,
  bsns_year          INT          NOT NULL,
  reprt_code         VARCHAR(8)   NOT NULL,
  fs_div             VARCHAR(8)   NOT NULL,       -- CFS, OFS
  rcept_no           VARCHAR(20),
  sj_div             VARCHAR(8),
  account_id         VARCHAR(200),
  account_nm         VARCHAR(200) NOT NULL,
  ord                INT,
  thstrm_nm          VARCHAR(64),
  thstrm_amount      VARCHAR(40),
  thstrm_add_amount  VARCHAR(40),
  frmtrm_nm          VARCHAR(64),
  frmtrm_amount      VARCHAR(40),
  frmtrm_q_amount    VARCHAR(40),
  frmtrm_add_amount  VARCHAR(40),
  bfefrmtrm_nm       VARCHAR(64),
  bfefrmtrm_amount   VARCHAR(40),
  currency           VARCHAR(8),
  UNIQUE KEY uk_ifl (corp_code, bsns_year, reprt_code, fs_div, sj_div, account_nm, ord),
  INDEX idx_ifl_lookup (corp_code, bsns_year, reprt_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 일별 시세(getStockPriceInfo). 종목코드 단위(보통주·우선주 각각)
CREATE TABLE IF NOT EXISTS ingest_market_daily (
  stock_code    VARCHAR(16)  NOT NULL,
  bas_dt        VARCHAR(8)   NOT NULL,
  itms_nm       VARCHAR(100),
  mrkt_ctg      VARCHAR(16),
  clpr          BIGINT,
  lstg_st_cnt   BIGINT,
  mrkt_tot_amt  BIGINT,
  PRIMARY KEY (stock_code, bas_dt),
  INDEX idx_imd_dt (bas_dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 지수 일별 종가(getStockMarketIndex)
CREATE TABLE IF NOT EXISTS ingest_index_daily (
  idx_nm  VARCHAR(32)  NOT NULL,
  bas_dt  VARCHAR(8)   NOT NULL,
  clpr    DECIMAL(14,2) NOT NULL,
  PRIMARY KEY (idx_nm, bas_dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 수집 실행 기록. 호출 예산 관리·재시도·관리 화면의 근거다(작업 단위 한 줄)
CREATE TABLE IF NOT EXISTS ingest_run (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_uid       VARCHAR(64)  NOT NULL,            -- 같은 실행의 단계들을 묶는다
  mode          VARCHAR(16)  NOT NULL,            -- daily, backfill
  step          VARCHAR(32)  NOT NULL,            -- companies, induty, filings, financials, documents, market, index
  status        VARCHAR(16)  NOT NULL,            -- RUNNING, DONE, PARTIAL(예산 소진), FAILED, SKIPPED
  source        VARCHAR(16)  NOT NULL,            -- sample, opendart
  calls         INT          NOT NULL DEFAULT 0,  -- 원천 API 호출 수(캐시 적중은 세지 않는다)
  rows_written  INT          NOT NULL DEFAULT 0,
  remaining     INT          NOT NULL DEFAULT 0,  -- 예산 때문에 다음 실행으로 넘긴 대상 수
  error_message TEXT,
  started_at    DATETIME(6)  NOT NULL,
  finished_at   DATETIME(6),
  INDEX idx_ir_uid (run_uid),
  INDEX idx_ir_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE USER IF NOT EXISTS 'gongsi_ingest'@'%' IDENTIFIED BY 'ingest-pass';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_company        TO 'gongsi_ingest'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_filing         TO 'gongsi_ingest'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_financial_line TO 'gongsi_ingest'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_market_daily   TO 'gongsi_ingest'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_index_daily    TO 'gongsi_ingest'@'%';
GRANT SELECT, INSERT, UPDATE ON gongsi.ingest_run            TO 'gongsi_ingest'@'%';
GRANT SELECT ON gongsi.kill_switch_status TO 'gongsi_ingest'@'%';   -- Kill Switch가 켜져 있으면 수집도 멈춘다

GRANT SELECT ON gongsi.ingest_company        TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.ingest_filing         TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.ingest_financial_line TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.ingest_market_daily   TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.ingest_index_daily    TO 'gongsi_app'@'%';
GRANT SELECT ON gongsi.ingest_run            TO 'gongsi_app'@'%';
FLUSH PRIVILEGES;
