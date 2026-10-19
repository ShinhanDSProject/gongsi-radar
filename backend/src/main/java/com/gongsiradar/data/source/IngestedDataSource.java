package com.gongsiradar.data.source;

import com.gongsiradar.data.support.Dart;
import com.gongsiradar.data.support.Rows;

import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;
import java.sql.Date;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 적재 DB(#3 일일 수집)를 먼저 보고, 없을 때만 원천을 부르는 소스(파이썬 {@code radar/ingest/dbsource.py}).
 * <p>
 * 전 종목이 필요한 조회(기업 목록·시세 이력·최근 공시·업종 코드)는 적재 DB가 있으면 그것만 읽는다 — 화면이 원천 API 호출
 * 한도에 묶이지 않는다. 회사 한 곳의 분석(재무)은 적재분이 있으면 쓰고, 없으면 원천을 부른다.
 * 원문·지배구조·피어·소송·보고서 찾기는 적재 대상이 아니라 원천에 그대로 맡긴다.
 * <p>
 * 반환 모양은 원천 소스와 같다(OpenDART·공공데이터포털 응답 필드). 적재 DB가 비어 있거나 읽을 수 없으면 원천을 그대로
 * 쓴다(수집 전에도 앱이 돈다). 읽기는 앱 계정(gongsi_app, 적재 테이블 SELECT만)으로 한다 — 쓰기는 수집 작업만 한다.
 */
@Slf4j
public class IngestedDataSource implements RadarSource {

    /** 재무 행에서 그대로 옮기는 금액·이름 필드(07_ingest_schema.sql ingest_financial_line) */
    public static final List<String> FIN_FIELDS = List.of("thstrm_nm", "thstrm_amount", "thstrm_add_amount", "frmtrm_nm",
            "frmtrm_amount", "frmtrm_q_amount", "frmtrm_add_amount", "bfefrmtrm_nm", "bfefrmtrm_amount", "currency");

    private final RadarSource base;
    private final JdbcTemplate jdbc;
    private final Clock clock;

    public IngestedDataSource(RadarSource base, DataSource dataSource, Clock clock) {
        this.base = base;
        this.jdbc = new JdbcTemplate(dataSource);
        this.clock = clock;
    }

    public RadarSource base() {
        return base;
    }

    private List<Map<String, Object>> rows(String sql, Object... args) {
        try {
            return jdbc.queryForList(sql, args);
        } catch (DataAccessException e) {
            log.warn("적재 DB 조회 실패({}) — 원천을 씁니다", e.getClass().getSimpleName());
            return List.of();
        }
    }

    // ───────────────────────── 원천에 맡기는 것 ─────────────────────────

    @Override
    public String name() {
        return base.name();
    }

    @Override
    public long calls() {
        return base.calls();
    }

    @Override
    public Map<String, Object> resolve(String query) {
        return base.resolve(query);
    }

    @Override
    public Map<String, Object> findReport(String corpCode, int bsnsYear, String reprtCode) {
        return base.findReport(corpCode, bsnsYear, reprtCode);
    }

    @Override
    public byte[] document(String rceptNo) {
        return base.document(rceptNo);
    }

    @Override
    public List<Map<String, Object>> peers(String corpCode, int bsnsYear, String reprtCode) {
        return base.peers(corpCode, bsnsYear, reprtCode);
    }

    @Override
    public List<Map<String, Object>> lawsuits(String corpCode, String bgn, String end) {
        return base.lawsuits(corpCode, bgn, end);
    }

    /**
     * 회사 정기공시 목록. 적재된 공시에 사업보고서가 있으면 적재 DB만으로 답한다(원천 호출 없음).
     * 적재가 덜 됐으면(일일 수집은 최근 공시만 받는다) 원천을 부르고, 원천이 실패하면 적재된 만큼이라도 돌려준다.
     */
    @Override
    public List<Map<String, Object>> filings(String corpCode) {
        List<Map<String, Object>> stored = storedFilings(corpCode);
        boolean hasAnnual = stored.stream().anyMatch(r -> "11011".equals(Rows.str(r, "reprt_code")));
        if (hasAnnual) {
            return stored;
        }
        try {
            return base.filings(corpCode);
        } catch (DataSourceException e) {
            if (!stored.isEmpty()) {
                log.info("원천 공시 목록 실패({}) — 적재된 {}건으로 답함: {}", e.getClass().getSimpleName(), stored.size(), corpCode);
                return stored;
            }
            throw e;
        }
    }

    private List<Map<String, Object>> storedFilings(String corpCode) {
        boolean docAvailable = "opendart".equals(base.name());   // OpenDART는 원문을 언제든 받을 수 있다
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows("SELECT rcept_no, corp_code, corp_name, stock_code, report_nm, rcept_dt, rm, has_document"
                + " FROM ingest_filing WHERE corp_code = ? ORDER BY rcept_dt DESC, rcept_no DESC", corpCode)) {
            Map<String, Object> raw = Rows.m("rcept_no", r.get("rcept_no"), "corp_code", r.get("corp_code"),
                    "corp_name", r.get("corp_name"), "stock_code", r.get("stock_code"), "report_nm", r.get("report_nm"),
                    "rcept_dt", r.get("rcept_dt"), "rm", r.get("rm"));
            Map<String, Object> row = Dart.filingRow(raw, docAvailable || Rows.truthy(r.get("has_document")));
            if (row != null) out.add(row);
        }
        return out;
    }

    @Override
    public Map<String, Object> governance(String corpCode, int bsnsYear, String reprtCode) {
        return base.governance(corpCode, bsnsYear, reprtCode);
    }

    /** 적재가 한 번이라도 돌았는가. 시장 화면의 ingested·신규 확인 기업 표시 기준. */
    @Override
    public boolean ingested() {
        try {
            Integer n = jdbc.queryForObject("SELECT COUNT(*) FROM ingest_company", Integer.class);
            return n != null && n > 0;
        } catch (DataAccessException e) {   // 테이블이 없거나 권한이 없으면 적재 DB를 쓰지 않는다
            return false;
        }
    }

    // ───────────────────────── 기업 ─────────────────────────

    @Override
    public List<Map<String, Object>> companies() {
        List<Map<String, Object>> rows = rows("SELECT corp_code, corp_name, stock_code, induty_code, market FROM ingest_company"
                + " WHERE listed = TRUE AND stock_code IS NOT NULL ORDER BY corp_code");
        if (rows.isEmpty()) {
            return base.companies();
        }
        // 업종 '설명'(샘플의 '2차전지 소재' 같은 표시용 문구)은 적재 대상이 아니다. 샘플일 때만 원천에서 붙인다.
        // 샘플이면 순서도 원천 목록 순서로 맞춘다 — 화면이 수집 전후로 달라지지 않게(실데이터는 고유번호 순)
        Map<String, Object> induty = new HashMap<>();
        Map<String, Integer> order = new HashMap<>();
        if ("sample".equals(base.name())) {
            List<Map<String, Object>> bc = base.companies();
            for (int i = 0; i < bc.size(); i++) {
                induty.put(Rows.str(bc.get(i), "corp_code"), bc.get(i).get("induty"));
                order.put(Rows.str(bc.get(i), "corp_code"), i);
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            String corp = Rows.str(r, "corp_code");
            out.add(Rows.m("corp_code", corp, "corp_name", r.get("corp_name"), "stock_code", r.get("stock_code"),
                    "induty", induty.get(corp), "induty_code", r.get("induty_code"), "market", r.get("market")));
        }
        if (!order.isEmpty()) {
            out.sort(Comparator.comparingInt(c -> order.getOrDefault(Rows.str(c, "corp_code"), Integer.MAX_VALUE)));
        }
        return out;
    }

    @Override
    public String indutyCode(String corpCode) {
        List<Map<String, Object>> rows = rows("SELECT induty_code FROM ingest_company WHERE corp_code = ?", corpCode);
        if (!rows.isEmpty() && Rows.truthy(rows.get(0).get("induty_code"))) {
            return Rows.str(rows.get(0), "induty_code");
        }
        return base.indutyCode(corpCode);
    }

    /** 최근 처음 확인한 기업. 첫 적재일(전 종목을 처음 넣은 날)에 들어온 회사는 '신규'가 아니다. */
    @Override
    public List<Map<String, Object>> newListings(int days) {
        List<Map<String, Object>> first = rows("SELECT MIN(first_seen) AS d FROM ingest_company");
        if (first.isEmpty() || first.get(0).get("d") == null) {
            return List.of();
        }
        LocalDate firstLoad = toDate(first.get(0).get("d"));
        LocalDate since = LocalDate.now(clock).minusDays(days);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows("SELECT corp_code, corp_name, stock_code, market, induty_code, first_seen, last_seen"
                + " FROM ingest_company WHERE first_seen > ? AND first_seen >= ? ORDER BY first_seen DESC", firstLoad, since)) {
            Map<String, Object> m = new LinkedHashMap<>();
            r.forEach((k, v) -> m.put(k.toLowerCase(), v instanceof Date || v instanceof java.sql.Timestamp ? toDate(v) : v));
            out.add(m);
        }
        return out;
    }

    static LocalDate toDate(Object v) {
        if (v instanceof LocalDate d) return d;
        if (v instanceof Date d) return d.toLocalDate();
        if (v instanceof java.sql.Timestamp t) return t.toLocalDateTime().toLocalDate();
        return LocalDate.parse(v.toString().substring(0, 10));
    }

    // ───────────────────────── 시세·지수 ─────────────────────────

    private static String s(Object v) {   // 원천 응답처럼 문자열로
        return v == null ? null : v.toString();
    }

    private static Map<String, Object> priceRow(Map<String, Object> r) {
        return Rows.m("basDt", r.get("bas_dt"), "srtnCd", r.get("stock_code"), "itmsNm", r.get("itms_nm"),
                "mrktCtg", r.get("mrkt_ctg"), "clpr", s(r.get("clpr")), "lstgStCnt", s(r.get("lstg_st_cnt")),
                "mrktTotAmt", s(r.get("mrkt_tot_amt")));
    }

    private static final String PRICE_COLS = "stock_code, bas_dt, itms_nm, mrkt_ctg, clpr, lstg_st_cnt, mrkt_tot_amt";

    @Override
    public Map<String, List<Map<String, Object>>> marketHistory() {
        List<Map<String, Object>> rows = rows("SELECT " + PRICE_COLS + " FROM ingest_market_daily");
        if (rows.isEmpty()) {
            return base.marketHistory();
        }
        Map<String, List<Map<String, Object>>> out = new LinkedHashMap<>();
        for (Map<String, Object> r : rows) {
            out.computeIfAbsent(Rows.str(r, "stock_code"), k -> new ArrayList<>()).add(priceRow(r));
        }
        return out;
    }

    @Override
    public List<Map<String, Object>> market(String stockCode) {
        List<Map<String, Object>> rows = rows("SELECT " + PRICE_COLS + " FROM ingest_market_daily WHERE stock_code = ?"
                + " ORDER BY bas_dt DESC", stockCode);
        if (rows.isEmpty()) {
            return base.market(stockCode);
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows) out.add(priceRow(r));
        return out;
    }

    @Override
    public List<Map<String, Object>> indexSeries(String name) {
        List<Map<String, Object>> rows = rows("SELECT bas_dt, clpr FROM ingest_index_daily WHERE idx_nm = ? ORDER BY bas_dt", name);
        if (rows.isEmpty()) {
            return base.indexSeries(name);
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            out.add(Rows.m("basDt", r.get("bas_dt"), "idxNm", name, "clpr", s(r.get("clpr"))));
        }
        return out;
    }

    // ───────────────────────── 공시·재무 ─────────────────────────

    /** 최신 접수순 200건. 기간으로 자르지 않는다 — 원천 소스와 같은 결과를 내야 화면이 수집 전후로 달라지지 않는다. */
    @Override
    public List<Map<String, Object>> recentFilings() {
        List<Map<String, Object>> rows = rows("SELECT rcept_no, corp_code, corp_name, stock_code, report_nm, rcept_dt, rm,"
                + " reprt_code, bsns_year, has_document FROM ingest_filing ORDER BY rcept_dt DESC, rcept_no DESC LIMIT 200");
        if (rows.isEmpty()) {
            return base.recentFilings();
        }
        boolean docCached = "opendart".equals(base.name());   // OpenDART는 원문을 언제든 받을 수 있다. 샘플은 보유한 것만
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            out.add(Rows.m("rcept_no", r.get("rcept_no"), "corp_code", r.get("corp_code"), "corp_name", r.get("corp_name"),
                    "stock_code", r.get("stock_code"), "report_nm", r.get("report_nm"), "rcept_dt", r.get("rcept_dt"),
                    "rm", r.get("rm"), "reprt_code", r.get("reprt_code"),
                    "bsns_year", r.get("bsns_year") == null ? null : ((Number) r.get("bsns_year")).intValue(),
                    "hasDocument", Rows.bool(r.get("has_document")) || docCached));
        }
        return out;
    }

    @Override
    public Financials financials(String corpCode, int bsnsYear, String reprtCode) {
        List<Map<String, Object>> rows = rows("SELECT * FROM ingest_financial_line WHERE corp_code = ? AND bsns_year = ?"
                + " AND reprt_code = ? ORDER BY ord, id", corpCode, bsnsYear, reprtCode);
        for (String fs : List.of("CFS", "OFS")) {
            List<Map<String, Object>> lines = new ArrayList<>();
            for (Map<String, Object> r : rows) {
                if (!fs.equals(r.get("fs_div"))) continue;
                Map<String, Object> m = Rows.m("rcept_no", r.get("rcept_no"), "reprt_code", reprtCode,
                        "bsns_year", String.valueOf(bsnsYear), "corp_code", corpCode,
                        "sj_div", Rows.orNull(Rows.str(r, "sj_div")), "account_id", r.get("account_id"),
                        "account_nm", r.get("account_nm"), "ord", s(r.get("ord")), "fs_div", fs);
                for (String c : FIN_FIELDS) {
                    if (r.get(c) != null) m.put(c, r.get(c));
                }
                lines.add(m);
            }
            if (!lines.isEmpty()) {
                return new Financials(lines, fs);
            }
        }
        return base.financials(corpCode, bsnsYear, reprtCode);
    }
}
