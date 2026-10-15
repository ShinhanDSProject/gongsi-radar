"""적재 테이블 정의(SQLAlchemy Core). 정본 DDL은 scripts/sql/07_ingest_schema.sql이고, 여기는 같은 모양을 코드로 둔다.

MariaDB에서는 DDL을 사람이 관리자 계정으로 적용한다(수집 계정에는 CREATE 권한이 없다).
테스트와 단독 실행(SQLite)에서만 create_all로 만든다.
"""
from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

company = sa.Table(
    "ingest_company", metadata,
    sa.Column("corp_code", sa.String(16), primary_key=True),
    sa.Column("corp_name", sa.String(100), nullable=False),
    sa.Column("stock_code", sa.String(16)),
    sa.Column("market", sa.String(16)),
    sa.Column("induty_code", sa.String(16)),
    sa.Column("induty_checked", sa.Date),
    sa.Column("listed", sa.Boolean, nullable=False, default=True),
    sa.Column("first_seen", sa.Date, nullable=False),
    sa.Column("last_seen", sa.Date, nullable=False),
)

filing = sa.Table(
    "ingest_filing", metadata,
    sa.Column("rcept_no", sa.String(20), primary_key=True),
    sa.Column("corp_code", sa.String(16), nullable=False),
    sa.Column("corp_name", sa.String(100)),
    sa.Column("stock_code", sa.String(16)),
    sa.Column("report_nm", sa.String(200), nullable=False),
    sa.Column("reprt_code", sa.String(8)),
    sa.Column("bsns_year", sa.Integer),
    sa.Column("rcept_dt", sa.String(8), nullable=False),
    sa.Column("rm", sa.String(32)),
    sa.Column("is_correction", sa.Boolean, nullable=False, default=False),
    sa.Column("has_document", sa.Boolean, nullable=False, default=False),
    sa.Column("financial_done", sa.Boolean, nullable=False, default=False),
)

FIN_FIELDS = ("thstrm_nm", "thstrm_amount", "thstrm_add_amount", "frmtrm_nm", "frmtrm_amount", "frmtrm_q_amount",
              "frmtrm_add_amount", "bfefrmtrm_nm", "bfefrmtrm_amount", "currency")

financial_line = sa.Table(
    "ingest_financial_line", metadata,
    sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
    sa.Column("corp_code", sa.String(16), nullable=False),
    sa.Column("bsns_year", sa.Integer, nullable=False),
    sa.Column("reprt_code", sa.String(8), nullable=False),
    sa.Column("fs_div", sa.String(8), nullable=False),
    sa.Column("rcept_no", sa.String(20)),
    sa.Column("sj_div", sa.String(8)),
    sa.Column("account_id", sa.String(200)),
    sa.Column("account_nm", sa.String(200), nullable=False),
    sa.Column("ord", sa.Integer),
    *(sa.Column(f, sa.String(64 if f.endswith("_nm") else 40)) for f in FIN_FIELDS),
    sa.UniqueConstraint("corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "account_nm", "ord", name="uk_ifl"),
)

market_daily = sa.Table(
    "ingest_market_daily", metadata,
    sa.Column("stock_code", sa.String(16), primary_key=True),
    sa.Column("bas_dt", sa.String(8), primary_key=True),
    sa.Column("itms_nm", sa.String(100)),
    sa.Column("mrkt_ctg", sa.String(16)),
    sa.Column("clpr", sa.BigInteger),
    sa.Column("lstg_st_cnt", sa.BigInteger),
    sa.Column("mrkt_tot_amt", sa.BigInteger),
)

index_daily = sa.Table(
    "ingest_index_daily", metadata,
    sa.Column("idx_nm", sa.String(32), primary_key=True),
    sa.Column("bas_dt", sa.String(8), primary_key=True),
    sa.Column("clpr", sa.Numeric(14, 2), nullable=False),
)

run = sa.Table(
    "ingest_run", metadata,
    sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
    sa.Column("run_uid", sa.String(64), nullable=False),
    sa.Column("mode", sa.String(16), nullable=False),
    sa.Column("step", sa.String(32), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("source", sa.String(16), nullable=False),
    sa.Column("calls", sa.Integer, nullable=False, default=0),
    sa.Column("rows_written", sa.Integer, nullable=False, default=0),
    sa.Column("remaining", sa.Integer, nullable=False, default=0),
    sa.Column("error_message", sa.Text),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("finished_at", sa.DateTime),
)

# Kill Switch는 Spring이 쓰는 테이블이다. SQLite 단독 실행·테스트에서만 같은 모양으로 만든다
kill_switch_status = sa.Table(
    "kill_switch_status", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("reason", sa.String(500)),
    sa.Column("toggled_by", sa.String(64), nullable=False),
)
