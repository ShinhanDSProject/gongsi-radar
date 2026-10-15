-- 수집 테스트용 H2(MariaDB 모드) 스키마. 정본은 db/schema/07_ingest_schema.sql — 같은 열·키를 H2 문법으로만 옮겼다
CREATE TABLE ingest_company (
  corp_code      VARCHAR(16)  PRIMARY KEY,
  corp_name      VARCHAR(100) NOT NULL,
  stock_code     VARCHAR(16),
  market         VARCHAR(16),
  induty_code    VARCHAR(16),
  induty_checked DATE,
  listed         BOOLEAN      NOT NULL DEFAULT TRUE,
  first_seen     DATE         NOT NULL,
  last_seen      DATE         NOT NULL,
  updated_at     TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE ingest_filing (
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
  financial_done  BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE ingest_financial_line (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  corp_code          VARCHAR(16)  NOT NULL,
  bsns_year          INT          NOT NULL,
  reprt_code         VARCHAR(8)   NOT NULL,
  fs_div             VARCHAR(8)   NOT NULL,
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
  CONSTRAINT uk_ifl UNIQUE (corp_code, bsns_year, reprt_code, fs_div, sj_div, account_nm, ord)
);
CREATE TABLE ingest_market_daily (
  stock_code    VARCHAR(16)  NOT NULL,
  bas_dt        VARCHAR(8)   NOT NULL,
  itms_nm       VARCHAR(100),
  mrkt_ctg      VARCHAR(16),
  clpr          BIGINT,
  lstg_st_cnt   BIGINT,
  mrkt_tot_amt  BIGINT,
  PRIMARY KEY (stock_code, bas_dt)
);
CREATE TABLE ingest_index_daily (
  idx_nm  VARCHAR(32)  NOT NULL,
  bas_dt  VARCHAR(8)   NOT NULL,
  clpr    DECIMAL(14,2) NOT NULL,
  PRIMARY KEY (idx_nm, bas_dt)
);
CREATE TABLE ingest_run (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_uid       VARCHAR(64)  NOT NULL,
  mode          VARCHAR(16)  NOT NULL,
  step          VARCHAR(32)  NOT NULL,
  status        VARCHAR(16)  NOT NULL,
  source        VARCHAR(16)  NOT NULL,
  calls         INT          NOT NULL DEFAULT 0,
  rows_written  INT          NOT NULL DEFAULT 0,
  remaining     INT          NOT NULL DEFAULT 0,
  error_message CLOB,
  started_at    TIMESTAMP(6) NOT NULL,
  finished_at   TIMESTAMP(6)
);
CREATE TABLE kill_switch_status (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  active      BOOLEAN      NOT NULL,
  reason      VARCHAR(500),
  toggled_by  VARCHAR(64)  NOT NULL,
  toggled_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
