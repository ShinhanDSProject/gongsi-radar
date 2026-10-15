package com.gongsiradar.ingest.repository;

import com.gongsiradar.data.support.Rows;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

import javax.sql.DataSource;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 적재 저장소(파이썬 {@code radar/ingest/store.py}). 테이블 정본은 {@code db/schema/07_ingest_schema.sql}.
 * <p>
 * 쓰기는 모두 upsert({@code INSERT ... ON DUPLICATE KEY UPDATE})다. 같은 날 두 번 돌려도 결과가 같아야 하고(멱등),
 * 수집 계정(gongsi_ingest)에는 DELETE 권한이 없다 — 상장폐지도 행을 지우지 않고 표시만 한다.
 * 수집 작업은 수집 계정 커넥션으로, 관리 화면 조회는 앱 계정 커넥션으로 같은 클래스를 쓴다.
 */
public class IngestStore {

    public static final String COMPANY = "ingest_company";
    public static final String FILING = "ingest_filing";
    public static final String FINANCIAL_LINE = "ingest_financial_line";
    public static final String MARKET_DAILY = "ingest_market_daily";
    public static final String INDEX_DAILY = "ingest_index_daily";
    public static final String RUN = "ingest_run";
    static final Set<String> TABLES = Set.of(COMPANY, FILING, FINANCIAL_LINE, MARKET_DAILY, INDEX_DAILY, RUN);

    private final JdbcTemplate jdbc;

    public IngestStore(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public JdbcTemplate jdbc() {
        return jdbc;
    }

    // ───────────────────────── upsert ─────────────────────────

    /**
     * rows를 넣고 키가 겹치면 update 열만 갱신한다. 넣거나 고친 행 수(대략 = 넘긴 행 수)를 돌려준다.
     * 모든 행은 같은 키 집합을 가져야 한다. 500행씩 배치로 보낸다.
     */
    public int upsert(String table, List<Map<String, Object>> rows, Collection<String> update) {
        if (rows.isEmpty()) return 0;
        if (!TABLES.contains(table)) throw new IllegalArgumentException("모르는 적재 테이블: " + table);
        List<String> cols = new ArrayList<>(rows.get(0).keySet());
        StringBuilder sql = new StringBuilder(update.isEmpty() ? "INSERT IGNORE INTO " : "INSERT INTO ")
                .append(table).append(" (").append(String.join(", ", cols)).append(") VALUES (")
                .append(String.join(", ", java.util.Collections.nCopies(cols.size(), "?"))).append(")");
        if (!update.isEmpty()) {
            sql.append(" ON DUPLICATE KEY UPDATE ");
            List<String> sets = new ArrayList<>();
            for (String c : update) sets.add(c + " = VALUES(" + c + ")");
            sql.append(String.join(", ", sets));
        }
        for (int k = 0; k < rows.size(); k += 500) {
            List<Object[]> batch = new ArrayList<>();
            for (Map<String, Object> r : rows.subList(k, Math.min(k + 500, rows.size()))) {
                Object[] args = new Object[cols.size()];
                for (int i = 0; i < cols.size(); i++) args[i] = r.get(cols.get(i));
                batch.add(args);
            }
            jdbc.batchUpdate(sql.toString(), batch);
        }
        return rows.size();
    }

    /** 처음 본 회사는 first_seen=오늘. 이미 있는 회사는 이름·종목코드·last_seen만 갱신한다(first_seen 유지). */
    public int upsertCompanies(List<Map<String, Object>> rows, LocalDate today) {
        List<Map<String, Object>> payload = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            String induty = Rows.orNull(Rows.str(r, "induty_code"));
            payload.add(Rows.m("corp_code", r.get("corp_code"), "corp_name", r.get("corp_name"),
                    "stock_code", Rows.orNull(Rows.str(r, "stock_code")), "market", Rows.str(r, "market"),
                    "induty_code", induty, "induty_checked", induty != null ? today : null,
                    "listed", true, "first_seen", today, "last_seen", today));
        }
        int n = upsert(COMPANY, payload, List.of("corp_name", "stock_code", "listed", "last_seen"));
        // 목록 자체에 업종·시장이 있으면(샘플) 비어 있는 칸만 채운다
        Map<List<String>, List<Object[]>> byCols = new LinkedHashMap<>();
        for (Map<String, Object> r : payload) {
            List<String> cols = new ArrayList<>();
            List<Object> args = new ArrayList<>();
            for (String k : List.of("market", "induty_code", "induty_checked")) {
                if (r.get(k) != null) {
                    cols.add(k);
                    args.add(r.get(k));
                }
            }
            if (cols.isEmpty()) continue;
            args.add(r.get("corp_code"));
            byCols.computeIfAbsent(cols, x -> new ArrayList<>()).add(args.toArray());
        }
        byCols.forEach((cols, batch) -> jdbc.batchUpdate("UPDATE " + COMPANY + " SET "
                + String.join(", ", cols.stream().map(c -> c + " = ?").toList())
                + " WHERE corp_code = ? AND (induty_code IS NULL OR market IS NULL)", batch));
        return n;
    }

    /** 오늘 목록에 없던 회사는 상장폐지 표시(행은 지우지 않는다 — 지난 공시·재무가 그 회사를 가리킨다). */
    public int markDelisted(Set<String> seen) {
        List<String> listed = jdbc.queryForList("SELECT corp_code FROM " + COMPANY + " WHERE listed = TRUE", String.class);
        List<Object[]> gone = new ArrayList<>();
        for (String c : listed) {
            if (!seen.contains(c)) gone.add(new Object[]{c});
        }
        if (!gone.isEmpty()) {
            jdbc.batchUpdate("UPDATE " + COMPANY + " SET listed = FALSE WHERE corp_code = ?", gone);
        }
        return gone.size();
    }

    // ───────────────────────── 조회 ─────────────────────────

    public int count(String table) {
        if (!TABLES.contains(table)) throw new IllegalArgumentException("모르는 적재 테이블: " + table);
        Integer n = jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Integer.class);
        return n == null ? 0 : n;
    }

    public boolean hasData() {
        try {
            return count(COMPANY) > 0;
        } catch (DataAccessException e) {   // 테이블이 없거나 권한이 없으면 적재 DB를 쓰지 않는다
            return false;
        }
    }

    public Map<String, String> latestMarketDates() {
        Map<String, String> out = new HashMap<>();
        jdbc.query("SELECT stock_code, MAX(bas_dt) AS d FROM " + MARKET_DAILY + " GROUP BY stock_code",
                rs -> {
                    out.put(rs.getString(1), rs.getString(2));
                });
        return out;
    }

    public record KillSwitch(boolean active, String reason) {
    }

    /** Kill Switch 최신 상태. 읽지 못하면 꺼진 것으로 본다(단독 실행). */
    public KillSwitch killSwitch() {
        try {
            List<Map<String, Object>> rows = jdbc.queryForList(
                    "SELECT active, reason FROM kill_switch_status ORDER BY id DESC LIMIT 1");
            if (rows.isEmpty()) return new KillSwitch(false, null);
            return new KillSwitch(Rows.bool(rows.get(0).get("active")), Rows.str(rows.get(0), "reason"));
        } catch (DataAccessException e) {
            return new KillSwitch(false, null);
        }
    }

    // ───────────────────────── 실행 기록 ─────────────────────────

    public long startRun(String runUid, String mode, String step, String source, LocalDateTime now) {
        KeyHolder kh = new GeneratedKeyHolder();
        jdbc.update(con -> {
            PreparedStatement ps = con.prepareStatement("INSERT INTO " + RUN + " (run_uid, mode, step, status, source, calls,"
                    + " rows_written, remaining, started_at) VALUES (?, ?, ?, 'RUNNING', ?, 0, 0, 0, ?)", Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, runUid);
            ps.setString(2, mode);
            ps.setString(3, step);
            ps.setString(4, source);
            ps.setObject(5, now);
            return ps;
        }, kh);
        // 드라이버마다 생성 키 이름이 다르다(MariaDB insert_id, H2 ID)
        Map<String, Object> keys = kh.getKeyList().get(0);
        Object id = keys.entrySet().stream()
                .filter(e -> e.getKey().equalsIgnoreCase("id") || e.getKey().equalsIgnoreCase("insert_id"))
                .map(Map.Entry::getValue).findFirst().orElse(keys.values().iterator().next());
        return ((Number) id).longValue();
    }

    public void finishRun(long runId, String status, int calls, int rows, int remaining, String error, LocalDateTime now) {
        jdbc.update("UPDATE " + RUN + " SET status = ?, calls = ?, rows_written = ?, remaining = ?, error_message = ?,"
                        + " finished_at = ? WHERE id = ?", status, calls, rows, remaining,
                error == null || error.isEmpty() ? null : error.substring(0, Math.min(2000, error.length())), now, runId);
    }

    public List<Map<String, Object>> recentRuns(int limit) {
        return jdbc.queryForList("SELECT id, run_uid, mode, step, status, source, calls, rows_written, remaining,"
                + " error_message, started_at, finished_at FROM " + RUN + " ORDER BY id DESC LIMIT ?", limit);
    }
}
