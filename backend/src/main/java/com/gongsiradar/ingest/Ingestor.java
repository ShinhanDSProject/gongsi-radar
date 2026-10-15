package com.gongsiradar.ingest;

import com.gongsiradar.data.Dart;
import com.gongsiradar.data.DataSourceException;
import com.gongsiradar.data.IngestedDataSource;
import com.gongsiradar.data.RadarSource;
import com.gongsiradar.data.Rows;
import lombok.extern.slf4j.Slf4j;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Supplier;

/**
 * 일일 수집 작업(파이썬 {@code radar/ingest/jobs.py}). 원천(OpenDART·공공데이터포털)에서 받아 적재 DB에 upsert한다.
 * <p>
 * 단계와 우선순위(호출 예산이 모자라면 뒤 단계부터 다음 날로 밀린다):
 * <ol>
 *   <li>companies  상장사 목록(corpCode.xml) — 신규 상장·상장폐지 표시</li>
 *   <li>filings    최근 정기공시(list.json) — 증분. backfill은 회사별 N년치</li>
 *   <li>market     시세(날짜별 전 종목) — 저장된 마지막 날짜 이후만</li>
 *   <li>index      지수 일별 종가</li>
 *   <li>financials 새로 접수된 보고서의 재무 — 같은 접수번호는 다시 부르지 않는다</li>
 *   <li>induty     업종 코드(기업개황) — 시가총액 큰 회사부터, 확인한 지 90일 지난 것만</li>
 *   <li>documents  원문 ZIP — 최근 정기공시만(원천 소스의 디스크 캐시에 보관)</li>
 * </ol>
 * 원칙
 * <ul>
 *   <li>멱등: 모든 쓰기는 upsert. 같은 날 두 번 돌려도 결과가 같다</li>
 *   <li>이어 하기: 예산이 떨어지면 그 단계는 PARTIAL로 남기고 남은 대상 수를 기록한다. 완료 표시가 DB에 있으므로
 *       다음 실행이 같은 조건으로 다시 고르면 아직 안 한 것부터 잡힌다</li>
 *   <li>호출 수는 {@link RadarSource#calls()} 증가분으로 센다. 캐시 적중은 호출이 아니다</li>
 *   <li>Kill Switch가 켜져 있으면 시작하지 않고, 단위 작업 50개마다 다시 확인한다</li>
 * </ul>
 */
@Slf4j
public class Ingestor {

    public static final List<String> STEPS = List.of("companies", "filings", "market", "index", "financials", "induty", "documents");
    static final List<String> INDEX_NAMES = List.of("코스피", "코스닥");
    static final int INDUTY_RECHECK_DAYS = 90;
    /** 접수 후 이 기간이 지나도 재무가 없으면(013) 더 부르지 않는다 */
    static final int FINANCIAL_GIVE_UP_DAYS = 30;
    private static final DateTimeFormatter YMD = DateTimeFormatter.BASIC_ISO_DATE;

    static class BudgetExhausted extends RuntimeException {
        BudgetExhausted() {
            super(null, null, false, false);
        }
    }

    static class KillSwitchOn extends RuntimeException {
        KillSwitchOn(String reason) {
            super(reason, null, false, false);
        }
    }

    /**
     * 원천 호출 예산. 실행을 시작한 뒤 calls(실제 API 호출 수)가 늘어난 만큼을 실시간으로 뺀다.
     * 단계가 끝날 때 더하면 한 단계 안에서 예산을 넘겨도 막지 못한다 — 재무 단계 하나가 하루 한도를 다 쓸 수 있다.
     */
    static class Budget {
        final int limit;
        final Supplier<Long> counter;
        final long start;

        Budget(int limit, Supplier<Long> counter) {
            this.limit = limit;
            this.counter = counter;
            this.start = counter.get();
        }

        long used() {
            return counter.get() - start;
        }

        long left() {
            return Math.max(0, limit - used());
        }

        void check() {
            if (left() <= 0) throw new BudgetExhausted();
        }
    }

    /** 단계 하나의 결과. remaining -1은 예산 때문에 시작도 못 해 대상 수를 세지 못했다는 뜻. */
    public static class StepResult {
        public final String step;
        public String status = "DONE";
        public int calls;
        public int rows;
        public int remaining;
        public String error;

        StepResult(String step) {
            this.step = step;
        }

        StepResult(String step, String status, String error) {
            this.step = step;
            this.status = status;
            this.error = error;
        }
    }

    public record RunReport(String runUid, String mode, List<StepResult> steps) {
        public int calls() {
            return steps.stream().mapToInt(s -> s.calls).sum();
        }

        public String summary() {
            List<String> parts = new ArrayList<>();
            for (StepResult s : steps) {
                parts.add(s.step + " " + s.status + "(호출 " + s.calls + ", 행 " + s.rows
                        + (s.remaining != 0 ? ", 남음 " + s.remaining : "") + ")");
            }
            return String.join(" · ", parts);
        }
    }

    private record Counts(int rows, int remaining) {
    }

    private final RadarSource src;
    private final IngestStore store;
    private final Budget budget;
    private final LocalDate today;
    private final Supplier<LocalDateTime> now;
    private final Consumer<StepResult> onStep;
    private int units;

    public Ingestor(RadarSource source, IngestStore store, int budget, LocalDate today, Supplier<LocalDateTime> now,
                    Consumer<StepResult> onStep) {
        this.src = source;
        this.store = store;
        this.budget = new Budget(budget, source::calls);
        this.today = today;
        this.now = now;
        this.onStep = onStep == null ? r -> { } : onStep;
    }

    // ───────────────────────── 공통 ─────────────────────────

    /** 단위 작업마다 부른다. 예산과 (50번마다) Kill Switch를 본다. */
    private void guard() {
        budget.check();
        units++;
        if (units % 50 == 0) {
            IngestStore.KillSwitch ks = store.killSwitch();
            if (ks.active()) throw new KillSwitchOn(ks.reason() == null || ks.reason().isEmpty() ? "Kill Switch" : ks.reason());
        }
    }

    public RunReport run(String mode) {
        return run(mode, STEPS, 3, true);
    }

    public RunReport run(String mode, List<String> steps, int years, boolean documents) {
        RunReport report = new RunReport("ing-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12), mode,
                new ArrayList<>());
        IngestStore.KillSwitch ks = store.killSwitch();
        if (ks.active()) {
            long rid = store.startRun(report.runUid(), mode, "all", src.name(), now.get());
            String err = "Kill Switch: " + (ks.reason() == null ? "" : ks.reason());
            store.finishRun(rid, "SKIPPED", 0, 0, 0, err, now.get());
            report.steps().add(new StepResult("all", "SKIPPED", err));
            return report;
        }
        for (String step : STEPS) {
            if (!steps.contains(step) || ("documents".equals(step) && !documents)) continue;
            StepResult res = new StepResult(step);
            long rid = store.startRun(report.runUid(), mode, step, src.name(), now.get());
            long before = src.calls();
            try {
                if (budget.left() <= 0) throw new BudgetExhausted();
                Counts c = switch (step) {
                    case "companies" -> stepCompanies();
                    case "filings" -> stepFilings(mode, years);
                    case "market" -> stepMarket();
                    case "index" -> stepIndex();
                    case "financials" -> stepFinancials();
                    case "induty" -> stepInduty();
                    default -> stepDocuments();
                };
                res.rows = c.rows();
                res.remaining = c.remaining();
                if (res.remaining != 0) res.status = "PARTIAL";
            } catch (BudgetExhausted e) {
                res.status = "PARTIAL";
                res.remaining = res.remaining != 0 ? res.remaining : -1;
            } catch (KillSwitchOn e) {
                res.status = "SKIPPED";
                res.error = "Kill Switch: " + e.getMessage();
            } catch (Exception e) {   // 한 단계 실패가 다른 단계를 막지 않는다
                log.error("수집 단계 실패: {}", step, e);
                res.status = "FAILED";
                res.error = e.getClass().getSimpleName() + ": " + e.getMessage();
            }
            res.calls = (int) (src.calls() - before);
            store.finishRun(rid, res.status, res.calls, res.rows, Math.max(res.remaining, 0), res.error, now.get());
            report.steps().add(res);
            onStep.accept(res);
            if ("SKIPPED".equals(res.status)) break;
        }
        return report;
    }

    // ───────────────────────── 단계 ─────────────────────────

    private Counts stepCompanies() {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> c : src.companies()) {
            if (Rows.truthy(c.get("stock_code"))) rows.add(c);
        }
        int n = store.upsertCompanies(rows, today);
        // 목록 전체를 받았을 때만 상장폐지를 표시한다(빈 응답·부분 응답으로 전부 지워지는 사고를 막는다)
        if (rows.size() >= 0.8 * Math.max(1, store.count(IngestStore.COMPANY))) {
            Set<String> seen = new HashSet<>();
            for (Map<String, Object> c : rows) seen.add(Rows.str(c, "corp_code"));
            store.markDelisted(seen);
        }
        return new Counts(n, 0);
    }

    private static Map<String, Object> filingPayload(Map<String, Object> r) {
        Dart.Kind k = Dart.reportKind(Rows.str(r, "report_nm", ""));
        if (k.code() == null) return null;
        String nm = Rows.str(r, "report_nm");
        String rm = Rows.orNull(Rows.str(r, "rm"));
        return Rows.m("rcept_no", r.get("rcept_no"), "corp_code", r.get("corp_code"), "corp_name", r.get("corp_name"),
                "stock_code", Rows.orNull(Rows.str(r, "stock_code")), "report_nm", nm, "reprt_code", k.code(),
                "bsns_year", k.year(), "rcept_dt", r.get("rcept_dt"), "rm", rm,
                "is_correction", nm.contains("정정") || (rm != null && rm.contains("정")),
                "has_document", Rows.truthy(r.get("hasDocument")), "financial_done", false);
    }

    private Counts stepFilings(String mode, int years) {
        List<Map<String, Object>> rows = new ArrayList<>();
        int remaining = 0;
        if ("backfill".equals(mode)) {
            // 회사별 지난 정기공시. 공시가 하나도 적재되지 않은 회사부터(이어 하기)
            Set<String> done = new HashSet<>(store.jdbc().queryForList(
                    "SELECT DISTINCT corp_code FROM " + IngestStore.FILING, String.class));
            List<String> corps = store.jdbc().queryForList(
                    "SELECT corp_code FROM " + IngestStore.COMPANY + " WHERE listed = TRUE", String.class);
            List<String> todo = corps.stream().filter(c -> !done.contains(c)).toList();
            String cutoff = (today.getYear() - years) + "0101";
            for (int k = 0; k < todo.size(); k++) {
                try {
                    guard();
                } catch (BudgetExhausted e) {
                    remaining = todo.size() - k;
                    break;
                }
                List<Map<String, Object>> lst;
                try {
                    lst = src.filings(todo.get(k));
                } catch (DataSourceException e) {
                    continue;
                }
                for (Map<String, Object> f : lst) {
                    if (Rows.str(f, "rcept_dt", "").compareTo(cutoff) >= 0) {
                        Map<String, Object> m = new LinkedHashMap<>(f);
                        m.put("corp_code", todo.get(k));
                        m.put("corp_name", null);
                        rows.add(m);
                    }
                }
            }
        } else {
            guard();
            rows = src.recentFilings();
        }
        List<Map<String, Object>> payload = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            Map<String, Object> p = filingPayload(r);
            if (p != null) payload.add(p);
        }
        // has_document·financial_done은 이미 true인 값을 덮어쓰지 않는다(update 목록에서 뺀다)
        int n = store.upsert(IngestStore.FILING, payload, List.of("report_nm", "rm", "is_correction"));
        return new Counts(n, remaining);
    }

    static Long toLong(Object v) {
        if (v == null) return null;
        String s = v.toString().replace(",", "");
        if (s.isEmpty() || s.equals("-")) return null;
        try {
            return (long) Double.parseDouble(s);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Counts stepMarket() {
        guard();
        Map<String, List<Map<String, Object>>> history = src.marketHistory();
        Map<String, String> last = store.latestMarketDates();
        List<Map<String, Object>> payload = new ArrayList<>();
        Map<String, String> marketOf = new LinkedHashMap<>();
        for (Map.Entry<String, List<Map<String, Object>>> e : history.entrySet()) {
            String code = e.getKey();
            String since = last.getOrDefault(code, "");
            for (Map<String, Object> r : e.getValue()) {
                String bas = Rows.str(r, "basDt");
                if (bas == null || bas.isEmpty() || bas.compareTo(since) <= 0) continue;
                payload.add(Rows.m("stock_code", code, "bas_dt", bas, "itms_nm", r.get("itmsNm"),
                        "mrkt_ctg", Rows.orNull(Rows.str(r, "mrktCtg", "").toUpperCase()), "clpr", toLong(r.get("clpr")),
                        "lstg_st_cnt", toLong(r.get("lstgStCnt")), "mrkt_tot_amt", toLong(r.get("mrktTotAmt"))));
            }
            if (!e.getValue().isEmpty()) {
                Map<String, Object> latest = e.getValue().stream()
                        .max(Comparator.comparing(x -> Rows.str(x, "basDt", ""))).orElseThrow();
                marketOf.put(code, Rows.orNull(Rows.str(latest, "mrktCtg", "").toUpperCase()));
            }
        }
        int n = store.upsert(IngestStore.MARKET_DAILY, payload, List.of("itms_nm", "mrkt_ctg", "clpr", "lstg_st_cnt", "mrkt_tot_amt"));
        // 회사의 시장 구분은 시세가 정본이다(상장 시장 이전이 있으면 따라간다)
        List<Object[]> upd = new ArrayList<>();
        marketOf.forEach((code, m) -> {
            if ("KOSPI".equals(m) || "KOSDAQ".equals(m) || "KONEX".equals(m)) upd.add(new Object[]{m, code});
        });
        if (!upd.isEmpty()) {
            store.jdbc().batchUpdate("UPDATE " + IngestStore.COMPANY + " SET market = ? WHERE stock_code = ?", upd);
        }
        return new Counts(n, 0);
    }

    private Counts stepIndex() {
        List<Map<String, Object>> payload = new ArrayList<>();
        for (String name : INDEX_NAMES) {
            guard();
            for (Map<String, Object> r : src.indexSeries(name)) {
                String clpr = Rows.str(r, "clpr");
                if (Rows.truthy(r.get("basDt")) && clpr != null && !clpr.isEmpty()) {
                    payload.add(Rows.m("idx_nm", name, "bas_dt", r.get("basDt"),
                            "clpr", Double.parseDouble(clpr.replace(",", ""))));
                }
            }
        }
        return new Counts(store.upsert(IngestStore.INDEX_DAILY, payload, List.of("clpr")), 0);
    }

    /** 재무를 아직 안 받은 정기공시. 같은 회사·연도·보고서의 최신 접수(정정 포함)만 한 번 받는다. */
    private Counts stepFinancials() {
        List<Map<String, Object>> todo = store.jdbc().queryForList("SELECT rcept_no, corp_code, bsns_year, reprt_code, rcept_dt FROM "
                + IngestStore.FILING + " WHERE financial_done = FALSE ORDER BY rcept_dt DESC");
        Set<String> seen = new HashSet<>();
        int rows = 0, remaining = 0;
        for (int k = 0; k < todo.size(); k++) {
            Map<String, Object> f = todo.get(k);
            String corp = Rows.str(f, "corp_code");
            Integer year = f.get("bsns_year") == null ? null : ((Number) f.get("bsns_year")).intValue();
            String reprt = Rows.str(f, "reprt_code");
            String rno = Rows.str(f, "rcept_no");
            String key = corp + "|" + year + "|" + reprt;
            if (seen.contains(key)) {
                mark(rno, "financial_done");   // 같은 기간의 이전 접수는 최신 것으로 대신한다
                continue;
            }
            seen.add(key);
            try {
                guard();
            } catch (BudgetExhausted e) {
                remaining = todo.size() - k;
                break;
            }
            RadarSource.Financials fin;
            try {
                if (year == null || reprt == null) throw new DataSourceException("보고서 종류를 알 수 없음");
                fin = src.financials(corp, year, reprt);
            } catch (DataSourceException e) {
                String dt = Rows.str(f, "rcept_dt");
                LocalDate filed = LocalDate.parse(dt, YMD);
                if (ChronoUnit.DAYS.between(filed, today) > FINANCIAL_GIVE_UP_DAYS) {
                    mark(rno, "financial_done");
                }
                continue;
            }
            List<Map<String, Object>> payload = new ArrayList<>();
            for (Map<String, Object> ln : fin.rows()) {
                Map<String, Object> p = Rows.m("corp_code", corp, "bsns_year", year, "reprt_code", reprt, "fs_div", fin.fsDiv(),
                        "rcept_no", Rows.truthy(ln.get("rcept_no")) ? Rows.str(ln, "rcept_no") : rno,
                        "sj_div", Rows.str(ln, "sj_div", ""), "account_id", Rows.str(ln, "account_id"),
                        "account_nm", Rows.str(ln, "account_nm", ""));
                Long ord = toLong(ln.get("ord"));
                p.put("ord", ord == null || ord == 0 ? 0 : ord.intValue());
                for (String c : IngestedDataSource.FIN_FIELDS) p.put(c, Rows.str(ln, c));
                payload.add(p);
            }
            List<String> update = new ArrayList<>(List.of("rcept_no", "account_id"));
            update.addAll(IngestedDataSource.FIN_FIELDS);
            rows += store.upsert(IngestStore.FINANCIAL_LINE, payload, update);
            mark(rno, "financial_done");
        }
        return new Counts(rows, remaining);
    }

    private Counts stepInduty() {
        LocalDate stale = today.minusDays(INDUTY_RECHECK_DAYS);
        Map<String, String> last = store.latestMarketDates();
        Map<String, Long> caps = new HashMap<>();
        store.jdbc().query("SELECT stock_code, bas_dt, mrkt_tot_amt FROM " + IngestStore.MARKET_DAILY, rs -> {
            String code = rs.getString(1);
            if (rs.getString(2).equals(last.get(code))) {
                long v = rs.getLong(3);
                caps.put(code, rs.wasNull() ? 0L : v);
            }
        });
        List<Map<String, Object>> todo = new ArrayList<>(store.jdbc().queryForList("SELECT corp_code, stock_code FROM "
                + IngestStore.COMPANY + " WHERE listed = TRUE AND (induty_checked IS NULL OR induty_checked < ?)", stale));
        todo.sort(Comparator.comparingLong(r -> -caps.getOrDefault(Rows.str(r, "stock_code"), 0L)));   // 업종 지도에 크게 보이는 회사부터
        int n = 0, remaining = 0;
        for (int k = 0; k < todo.size(); k++) {
            try {
                guard();
            } catch (BudgetExhausted e) {
                remaining = todo.size() - k;
                break;
            }
            String corp = Rows.str(todo.get(k), "corp_code");
            String code = src.indutyCode(corp);
            store.jdbc().update("UPDATE " + IngestStore.COMPANY + " SET induty_code = ?, induty_checked = ? WHERE corp_code = ?",
                    code, today, corp);
            n++;
        }
        return new Counts(n, remaining);
    }

    /** 최근 90일 정기공시 원문. 원문은 소스의 디스크 캐시에 남고 여기서는 보유 여부만 표시한다. */
    private Counts stepDocuments() {
        String cutoff = today.minusDays(90).format(YMD);
        List<String> todo = store.jdbc().queryForList("SELECT rcept_no FROM " + IngestStore.FILING
                + " WHERE has_document = FALSE AND rcept_dt >= ? ORDER BY rcept_dt DESC", String.class, cutoff);
        int n = 0, remaining = 0;
        for (int k = 0; k < todo.size(); k++) {
            try {
                guard();
            } catch (BudgetExhausted e) {
                remaining = todo.size() - k;
                break;
            }
            try {
                src.document(todo.get(k));
            } catch (DataSourceException e) {
                continue;
            }
            mark(todo.get(k), "has_document");
            n++;
        }
        return new Counts(n, remaining);
    }

    private void mark(String rceptNo, String column) {
        store.jdbc().update("UPDATE " + IngestStore.FILING + " SET " + column + " = TRUE WHERE rcept_no = ?", rceptNo);
    }
}
