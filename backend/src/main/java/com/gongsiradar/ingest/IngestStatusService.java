package com.gongsiradar.ingest;

import com.gongsiradar.data.DataSourceConfig;
import com.gongsiradar.data.Rows;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

import javax.sql.DataSource;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 일일 수집(#3) 상태 — 관리 화면용(CONTRACT §10). 적재 DB를 앱 계정으로 읽기만 한다.
 * <p>
 * 응답 모양은 분리 전 AI 서버 {@code /ai/ingest/status}와 같다:
 * {@code {enabled, reason, budget, callsToday, budgetLeft, lastMarketDate, tables, lastRun, runs[], steps[]}}.
 */
@Service
public class IngestStatusService {

    private static final List<String> TABLES = List.of(IngestStore.COMPANY, IngestStore.FILING, IngestStore.FINANCIAL_LINE,
            IngestStore.MARKET_DAILY, IngestStore.INDEX_DAILY);

    private final IngestStore store;
    private final int budget;

    public IngestStatusService(DataSource appDataSource, @Value("${gongsi.ingest.budget:15000}") int budget) {
        this.store = new IngestStore(appDataSource);
        this.budget = budget;
    }

    private static LocalDateTime ldt(Object v) {
        if (v == null) return null;
        if (v instanceof LocalDateTime t) return t;
        if (v instanceof Timestamp t) return t.toLocalDateTime();
        return LocalDateTime.parse(v.toString().replace(' ', 'T'));
    }

    private static int num(Object v) {
        return v == null ? 0 : ((Number) v).intValue();
    }

    public Map<String, Object> status() {
        List<Map<String, Object>> runs;
        Map<String, Object> tables = new LinkedHashMap<>();
        String lastMarket;
        try {
            runs = store.recentRuns(200);
            for (String t : TABLES) tables.put(t, store.count(t));
            lastMarket = store.jdbc().queryForObject("SELECT MAX(bas_dt) FROM " + IngestStore.MARKET_DAILY, String.class);
        } catch (DataAccessException e) {
            return Rows.m("enabled", false, "reason", "적재 테이블을 읽지 못했습니다(" + e.getClass().getSimpleName()
                            + "). scripts/sql/07_ingest_schema.sql 적용 여부를 확인하세요.",
                    "runs", List.of(), "steps", List.of(), "tables", Map.of(), "budget", budget);
        }
        if (runs.isEmpty()) {
            return Rows.m("enabled", true, "reason",
                    "아직 수집을 한 번도 돌리지 않았습니다(backend에서 ./gradlew bootRun --args='--gongsi.ingest.run-once=daily').",
                    "runs", List.of(), "steps", List.of(), "tables", tables, "budget", budget, "callsToday", 0, "budgetLeft", budget);
        }
        LocalDateTime midnight = LocalDate.now(DataSourceConfig.ZONE).atStartOfDay();
        int callsToday = 0;
        for (Map<String, Object> r : runs) {
            LocalDateTime st = ldt(r.get("started_at"));
            if (st != null && !st.isBefore(midnight)) callsToday += num(r.get("calls"));
        }
        String lastUid = Rows.str(runs.get(0), "run_uid");
        List<Map<String, Object>> steps = new ArrayList<>();
        Map<String, Map<String, Object>> byRun = new LinkedHashMap<>();
        Map<String, List<String>> statuses = new LinkedHashMap<>();
        for (Map<String, Object> r : runs) {
            String uid = Rows.str(r, "run_uid");
            LocalDateTime st = ldt(r.get("started_at"));
            LocalDateTime fin = ldt(r.get("finished_at"));
            Map<String, Object> g = byRun.computeIfAbsent(uid, k -> Rows.m("runUid", uid, "mode", r.get("mode"),
                    "source", r.get("source"), "startedAt", st, "finishedAt", fin, "calls", 0, "rows", 0));
            g.put("calls", num(g.get("calls")) + num(r.get("calls")));
            g.put("rows", num(g.get("rows")) + num(r.get("rows_written")));
            statuses.computeIfAbsent(uid, k -> new ArrayList<>()).add(Rows.str(r, "status"));
            if (st != null && (g.get("startedAt") == null || st.isBefore((LocalDateTime) g.get("startedAt")))) {
                g.put("startedAt", st);
            }
            if (fin != null && (g.get("finishedAt") == null || fin.isAfter((LocalDateTime) g.get("finishedAt")))) {
                g.put("finishedAt", fin);
            }
            if (uid.equals(lastUid)) {
                steps.add(Rows.m("step", r.get("step"), "status", r.get("status"), "calls", num(r.get("calls")),
                        "rows", num(r.get("rows_written")), "remaining", num(r.get("remaining")),
                        "error", r.get("error_message"), "finishedAt", fin));
            }
        }
        Collections.reverse(steps);
        List<Map<String, Object>> runRows = new ArrayList<>();
        for (Map<String, Object> g : byRun.values()) {
            if (runRows.size() >= 10) break;
            Map<String, Object> row = new LinkedHashMap<>(g);
            row.put("status", overall(statuses.get(Rows.str(g, "runUid"))));
            runRows.add(row);
        }
        return Rows.m("enabled", true, "reason", null, "budget", budget, "callsToday", callsToday,
                "budgetLeft", Math.max(0, budget - callsToday), "lastMarketDate", lastMarket, "tables", tables,
                "lastRun", runRows.get(0), "runs", runRows, "steps", steps);
    }

    private static String overall(List<String> sts) {
        for (String s : List.of("FAILED", "SKIPPED", "PARTIAL", "RUNNING")) {
            if (sts.contains(s)) return s;
        }
        return "DONE";
    }
}
