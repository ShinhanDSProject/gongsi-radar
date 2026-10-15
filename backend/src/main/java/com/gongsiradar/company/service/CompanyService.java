package com.gongsiradar.company.service;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.data.source.DataSourceException;
import com.gongsiradar.data.source.RadarSource;
import com.gongsiradar.data.support.Rows;
import com.gongsiradar.finance.Valuations;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import static com.gongsiradar.finance.Formulas.amount;
import static com.gongsiradar.finance.Formulas.finSource;
import static com.gongsiradar.finance.Formulas.formula;
import static com.gongsiradar.finance.Formulas.inp;
import static com.gongsiradar.finance.Formulas.pyRound;
import static com.gongsiradar.finance.Formulas.ratio;
import static com.gongsiradar.finance.Formulas.src;

/**
 * 기업 목록·검색과 기업 상세(CompanyRow·CompanyProfile, CONTRACT §6.6). 파이썬 {@code radar/company.py}를 옮겼다.
 * <p>
 * 상세 = 재무 다년 표(계산식·출처 포함) + 시장 지표 + 정기보고서 목록 — 여기까지 Java가 계산한다.
 * 원문에서 뽑는 사업 지표·지배구조 변동(business·governance)은 문서 분석이라 AI 서버 {@code GET /ai/insights/{corpCode}}가
 * 만든다. AI 서버가 응답하지 않아도 화면은 떠야 하므로 그 두 칸만 비우고 사유를 notes에 남긴다.
 * <p>
 * 금액 단위는 원. 값이 없으면 null이고 계산식에 '계산 안 함' 사유가 붙는다.
 */
@Slf4j
@Service
public class CompanyService {

    static final String[][] PROFILE_ACCOUNTS = {{"rev", "매출액"}, {"op", "영업이익"}, {"ni", "당기순이익"},
            {"ni_owner", "지배주주순이익"}, {"assets", "자산총계"}, {"liab", "부채총계"}, {"equity", "자본총계"}};
    /** (필드, 기준 연도에서 뺄 해) */
    static final Object[][] COLS = {{"bfefrmtrm_amount", 2}, {"frmtrm_amount", 1}, {"thstrm_amount", 0}};
    /** OpenDART: 검색 결과가 이보다 많으면 지표를 계산하지 않는다(회사마다 API 여러 번) */
    static final int METRICS_LIMIT = 10;
    public static final String NO_MARKET_SCOPE_NOTE = "MARKET_DATA_READ 권한이 없어 시장 지표를 표시하지 않습니다.";

    private final RadarSource source;
    private final AiClient aiClient;
    private final Clock clock;

    public CompanyService(RadarSource source, AiClient aiClient, Clock clock) {
        this.source = source;
        this.aiClient = aiClient;
        this.clock = clock;
    }

    private LocalDate today() {
        return LocalDate.now(clock);
    }

    // ───────────────────────── 목록 ─────────────────────────

    private static boolean match(Map<String, Object> c, String q) {
        if (q == null || q.isEmpty()) return true;
        q = q.strip().toLowerCase(Locale.ROOT);
        return Rows.str(c, "corp_name", "").toLowerCase(Locale.ROOT).contains(q)
                || Rows.str(c, "stock_code", "").startsWith(q)
                || q.equals(c.get("corp_code"));
    }

    /** 최신 거래일의 시가총액(원)과 그 날짜. 시세가 없으면 (null, null). */
    private record Cap(Long cap, String day) {
    }

    private Cap latestCap(Map<String, Object> c) {
        if (!Rows.truthy(c.get("stock_code"))) return new Cap(null, null);
        List<Map<String, Object>> rows;
        try {
            rows = source.market(Rows.str(c, "stock_code"));
        } catch (DataSourceException e) {
            return new Cap(null, null);
        }
        if (rows == null || rows.isEmpty()) return new Cap(null, null);
        Map<String, Object> last = rows.get(0);
        for (Map<String, Object> r : rows) {   // max: 같은 값이면 앞의 것
            if (Rows.str(r, "basDt", "").compareTo(Rows.str(last, "basDt", "")) > 0) last = r;
        }
        Long cap = amount(last.get("mrktTotAmt"));
        Long clpr = amount(last.get("clpr"));
        Long shares = amount(last.get("lstgStCnt"));
        if (cap == null && clpr != null && clpr != 0 && shares != null && shares != 0) {
            cap = clpr * shares;
        }
        String d = Rows.str(last, "basDt", "");
        return new Cap(cap, d.length() == 8 ? d.substring(0, 4) + "-" + d.substring(4, 6) + "-" + d.substring(6) : null);
    }

    private static Map<String, Object> baseRow(Map<String, Object> c) {
        return Rows.m("corpCode", c.get("corp_code"), "corpName", c.get("corp_name"),
                "stockCode", Rows.str(c, "stock_code", ""), "induty", c.get("induty"), "hasFilings", false,
                "revenue", null, "opIncome", null, "opMarginPct", null, "marketCap", null, "per", null, "pbr", null,
                "basis", null);
    }

    /** 회사 한 곳의 목록 행(지표 포함). */
    Map<String, Object> companyRow(Map<String, Object> c, LocalDate asOf) {
        Map<String, Object> row = baseRow(c);
        try {
            row.put("hasFilings", !source.filings(Rows.str(c, "corp_code")).isEmpty());
        } catch (DataSourceException ignored) {
            // 목록 조회 실패는 hasFilings=false
        }
        Valuations.Inputs vi = Valuations.gather(source, c, asOf);
        Valuations.Period a = vi.annual();
        if (a == null) {
            // 재무가 없어도 시가총액은 시세에서 나온다(PER·PBR은 분모가 없어 비운다)
            Cap cap = latestCap(c);
            row.put("marketCap", cap.cap());
            row.put("basis", "재무 데이터 없음" + (cap.cap() != null && cap.cap() != 0 ? " · 시가총액 시세 " + cap.day() : ""));
            return row;
        }
        Map<String, Object> rv = Valuations.findRow(a.rows(), "rev");
        Map<String, Object> op = Valuations.findRow(a.rows(), "op");
        Long revenue = rv != null ? amount(rv.get("thstrm_amount")) : null;
        Long opIncome = op != null ? amount(op.get("thstrm_amount")) : null;
        row.put("revenue", revenue);
        row.put("opIncome", opIncome);
        Double m = ratio(opIncome, revenue);
        row.put("opMarginPct", m != null ? pyRound(m * 100, 2) : null);
        Map<String, Object> val = Valuations.fromInputs(vi);
        row.put("marketCap", Valuations.metric(val, "market_cap"));
        row.put("per", Valuations.metric(val, "per_ttm"));
        row.put("pbr", Valuations.metric(val, "pbr"));
        row.put("basis", "매출·영업이익 " + a.year() + " 사업보고서(" + a.fs() + ")"
                + (val != null && val.get("asOf") != null ? " · PER(TTM)·PBR 시세 " + val.get("asOf") : " · 시세 없음"));
        return row;
    }

    /**
     * CompanyRow[]. 이름 부분 일치·종목코드 앞자리·고유번호로 찾는다.
     * <p>
     * 지표 계산: 샘플은 항상, OpenDART는 결과가 {@value #METRICS_LIMIT}개 이하일 때만.
     * 지표를 계산하지 않은 행은 hasFilings를 상장사 기준 true로 두고 basis에 사유를 적는다.
     */
    public List<Map<String, Object>> search(String q, int limit) {
        return search(q, limit, null, today());
    }

    public List<Map<String, Object>> search(String q, int limit, Boolean withMetrics, LocalDate asOf) {
        List<Map<String, Object>> corps = new ArrayList<>();
        for (Map<String, Object> c : source.companies()) {
            if (corps.size() >= Math.max(0, limit)) break;
            if (match(c, q)) corps.add(c);
        }
        boolean metrics = withMetrics != null ? withMetrics
                : "sample".equals(source.name()) || corps.size() <= METRICS_LIMIT;
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> c : corps) {
            if (metrics) {
                out.add(companyRow(c, asOf));
            } else {
                Map<String, Object> r = baseRow(c);
                r.put("hasFilings", true);
                r.put("basis", "검색 결과가 " + METRICS_LIMIT + "개를 넘어 지표를 계산하지 않음(검색어를 좁히세요)");
                out.add(r);
            }
        }
        return out;
    }

    // ───────────────────────── 상세 ─────────────────────────

    static Map<String, Object> financialTable(Valuations.Period annual) {
        if (annual == null) {
            return Rows.m("fsDiv", null, "columns", List.of(), "rows", List.of());
        }
        int y = annual.year();
        List<Map<String, Object>> rows = annual.rows();
        String fs = annual.fs();
        List<String> fields = new ArrayList<>();
        List<Integer> years = new ArrayList<>();
        for (Object[] col : COLS) {   // 전전기 칸이 비어 있으면 열을 뺀다
            String f = (String) col[0];
            boolean any = rows.stream().anyMatch(r -> amount(r.get(f)) != null);
            if (any) {
                fields.add(f);
                years.add(y - (Integer) col[1]);
            }
        }
        List<Map<String, Object>> table = new ArrayList<>();
        Map<String, List<Long>> vals = new java.util.HashMap<>();
        for (String[] acct : PROFILE_ACCOUNTS) {
            String key = acct[0], label = acct[1];
            Map<String, Object> r = Valuations.findRow(rows, key);
            List<Long> values = new ArrayList<>();
            List<Map<String, Object>> fms = new ArrayList<>();
            for (int k = 0; k < fields.size(); k++) {
                String f = fields.get(k);
                int yr = years.get(k);
                Long v = r != null ? amount(r.get(f)) : null;
                values.add(v);
                fms.add(formula(key + "_" + yr, label + "(" + yr + ")", "재무 API 값",
                        List.of(inp(label, v, "원", finSource(r, f, yr + " " + label + " (" + fs + ")", null))),
                        v, "원", v != null ? null : (r == null ? "재무 API에 해당 계정 없음" : "해당 기간 값 없음"), null, null));
            }
            vals.put(key, values);
            table.add(Rows.m("account", label, "values", values, "formulas", fms));
        }
        List<Double> margins = new ArrayList<>();
        List<Map<String, Object>> fms = new ArrayList<>();
        for (int k = 0; k < fields.size(); k++) {
            int yr = years.get(k);
            Long op = vals.get("op").get(k);
            Long rv = vals.get("rev").get(k);
            Double m = ratio(op, rv);
            margins.add(m != null ? pyRound(m * 100, 2) : null);
            fms.add(formula("op_margin_" + yr, "영업이익률(" + yr + ")", "영업이익 ÷ 매출액 × 100",
                    List.of(inp("영업이익", op, "원", src("계산", yr + " 영업이익")),
                            inp("매출액", rv, "원", src("계산", yr + " 매출액"))),
                    m != null ? m * 100 : null, "%", m != null ? null : "영업이익 또는 매출액이 없거나 매출액이 0", null, 2));
        }
        table.add(Rows.m("account", "영업이익률(%)", "values", margins, "formulas", fms));
        return Rows.m("fsDiv", fs, "columns", years.stream().map(String::valueOf).toList(), "rows", table);
    }

    /**
     * CompanyProfile. includeValuation=false면 시장 지표를 만들지 않고 valuationNote에 사유(권한 없음)를 남긴다.
     * 회사를 찾지 못하면 404.
     */
    public Map<String, Object> profile(String corpCode, boolean includeValuation, String userId, List<String> scopes) {
        return profile(corpCode, includeValuation, userId, scopes, today());
    }

    public Map<String, Object> profile(String corpCode, boolean includeValuation, String userId, List<String> scopes,
                                       LocalDate asOf) {
        Map<String, Object> c = null;
        for (Map<String, Object> x : source.companies()) {
            if (corpCode.equals(x.get("corp_code"))) {
                c = x;
                break;
            }
        }
        if (c == null) {
            try {
                c = source.resolve(corpCode);
            } catch (DataSourceException e) {
                throw new ApiException(ErrorCode.NOT_FOUND, "회사를 찾지 못했습니다: " + corpCode, e.getMessage());
            }
        }
        String corp = Rows.str(c, "corp_code");
        Map<String, Object> company = Rows.m("corpCode", corp, "corpName", c.get("corp_name"),
                "stockCode", Rows.str(c, "stock_code", ""), "induty", c.get("induty"));
        List<String> notes = new ArrayList<>();
        List<Map<String, Object>> filings;
        try {
            filings = source.filings(corp);
        } catch (DataSourceException e) {
            filings = List.of();
            notes.add("공시 목록 조회 실패: " + e.getMessage());
        }

        Valuations.Inputs vi = Valuations.gather(source, c, asOf);
        Map<String, Object> fin = financialTable(vi.annual());
        if (vi.annual() == null) {
            notes.add("사업보고서 재무 데이터가 없어 재무 표를 만들지 못함");
        }

        Map<String, Object> valuation = null;
        String valuationNote = null;
        if (includeValuation) {
            valuation = Valuations.fromInputs(vi);
            if (valuation == null) {
                valuationNote = "연간 재무 데이터가 없어 시장 지표를 계산하지 않음";
            }
        } else {
            valuationNote = NO_MARKET_SCOPE_NOTE;
        }

        // 사업 지표·지배구조: 원문 분석이라 AI 서버가 만든다. 실패해도 나머지는 그대로 보여 준다
        Object business = null;
        Object governance = null;
        try {
            Map<String, Object> ins = aiClient.insights(corp, userId, scopes);
            if (ins != null) {
                business = ins.get("business");
                governance = ins.get("governance");
                if (ins.get("notes") instanceof List<?> l) {
                    for (Object n : l) {
                        if (n != null) notes.add(n.toString());
                    }
                }
            }
        } catch (ApiException e) {
            log.warn("AI insights 실패: corp={} {} {}", corp, e.getErrorCode(), e.getMessage());
            notes.add("사업 지표·지배구조: AI 서버에서 받지 못해 표시하지 않음(" + e.getMessage() + ")");
        } catch (RuntimeException e) {
            log.warn("AI insights 실패: corp={}", corp, e);
            notes.add("사업 지표·지배구조: AI 서버에서 받지 못해 표시하지 않음(" + e.getClass().getSimpleName() + ")");
        }
        notes.add("금액 단위는 원입니다. 숫자마다 계산식·출처를 펼쳐 볼 수 있습니다.");

        List<Map<String, Object>> filingRows = new ArrayList<>();
        for (Map<String, Object> f : filings) {
            filingRows.add(Rows.m("rceptNo", f.get("rcept_no"), "reportNm", f.get("report_nm"), "rceptDt", f.get("rcept_dt"),
                    "reprtCode", f.get("reprt_code"), "bsnsYear", f.get("bsns_year"), "hasDocument", f.get("hasDocument")));
        }
        return Rows.m("company", company, "filings", filingRows, "financials", fin, "valuation", valuation,
                "valuationNote", valuation == null ? valuationNote : null,
                "business", business, "governance", governance, "notes", notes);
    }
}
