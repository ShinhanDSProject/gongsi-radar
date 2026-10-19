package com.gongsiradar.finance;

import com.gongsiradar.data.support.Dart;
import com.gongsiradar.data.source.DataSourceException;
import com.gongsiradar.data.source.SourceUnavailableException;
import com.gongsiradar.data.source.RadarSource;
import com.gongsiradar.data.support.Rows;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static com.gongsiradar.finance.Formulas.amount;
import static com.gongsiradar.finance.Formulas.finSource;
import static com.gongsiradar.finance.Formulas.formula;
import static com.gongsiradar.finance.Formulas.inp;
import static com.gongsiradar.finance.Formulas.ratio;
import static com.gongsiradar.finance.Formulas.src;

/**
 * 시장 지표: 시가총액·TTM·PER·PBR(알파인더 규칙, CONTRACT §6.5). 파이썬 {@code radar/numbers/valuation.py}를 옮겼다.
 * <ul>
 *   <li>TTM = 최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적(같은 연결·별도 범위)</li>
 *   <li>PER = 시가총액 ÷ 지배주주 순이익(TTM, 연간 두 가지). 이익 ≤ 0이면 계산 안 함</li>
 *   <li>PBR = 시가총액 ÷ 최근 기말 지배주주 자본. 자본 ≤ 0이면 계산 안 함</li>
 *   <li>지배주주 계정이 없으면 전체 계정(당기순이익·자본총계)으로 대체하고 입력값 note에 '대체 계정'을 남긴다</li>
 * </ul>
 * 수집({@link #gather})과 계산({@link #fromInputs})을 나눴다. 판단 문구는 만들지 않는다.
 */
public final class Valuations {

    private Valuations() {
    }

    static final List<String> INTERIM_ORDER = List.of("11014", "11012", "11013");   // 3분기 → 반기 → 1분기
    static final Set<String> FLOW = Set.of("IS", "CIS");
    static final Set<String> STOCK = Set.of("BS");

    record Acct(Set<String> sjs, Set<String> ids, List<String> names) {
    }

    static final Map<String, Acct> ACCOUNTS = new LinkedHashMap<>();
    static final Map<String, String> FALLBACK = Map.of("ni_owner", "ni", "equity_owner", "equity");
    public static final Map<String, String> NAMES = Map.of("rev", "매출액", "op", "영업이익", "ni", "당기순이익",
            "ni_owner", "지배주주 순이익", "equity", "자본총계", "equity_owner", "지배주주 자본", "assets", "자산총계",
            "liab", "부채총계");

    static {
        ACCOUNTS.put("rev", new Acct(FLOW, Set.of("ifrs-full_Revenue"), List.of("매출액", "수익(매출액)", "영업수익")));
        ACCOUNTS.put("op", new Acct(FLOW, Set.of("dart_OperatingIncomeLoss"), List.of("영업이익", "영업이익(손실)")));
        ACCOUNTS.put("ni", new Acct(FLOW, Set.of("ifrs-full_ProfitLoss"), List.of("당기순이익", "당기순이익(손실)")));
        ACCOUNTS.put("ni_owner", new Acct(FLOW, Set.of("ifrs-full_ProfitLossAttributableToOwnersOfParent"),
                List.of("지배기업의 소유주에게 귀속되는 당기순이익", "지배기업의 소유주에게 귀속되는 당기순이익(손실)",
                        "지배기업 소유주지분", "지배기업의 소유주지분", "지배기업소유주지분순이익")));
        ACCOUNTS.put("assets", new Acct(STOCK, Set.of("ifrs-full_Assets"), List.of("자산총계")));
        ACCOUNTS.put("liab", new Acct(STOCK, Set.of("ifrs-full_Liabilities"), List.of("부채총계")));
        ACCOUNTS.put("equity", new Acct(STOCK, Set.of("ifrs-full_Equity"), List.of("자본총계")));
        ACCOUNTS.put("equity_owner", new Acct(STOCK, Set.of("ifrs-full_EquityAttributableToOwnersOfParent"),
                List.of("지배기업의 소유주에게 귀속되는 자본", "지배기업 소유주지분", "지배기업의 소유주지분")));
    }

    /** 한 시점의 재무(연간 또는 중간). */
    public record Period(int year, String reprtCode, List<Map<String, Object>> rows, String fs, String rceptNo) {
    }

    /** 시장 지표 계산에 필요한 원자료. */
    public record Inputs(Map<String, Object> company, String asOf, Period annual, Period interim,
                         List<Map<String, Object>> prices, String marketSource, List<String> notes) {
    }

    // ───────────────────────── 계정 찾기 ─────────────────────────

    /** 표준계정 ID 우선, 없으면 계정명(공백 무시)으로. 다중회사 주요계정 행은 account_id가 없다. */
    public static Map<String, Object> findRow(List<Map<String, Object>> rows, String key) {
        Acct a = ACCOUNTS.get(key);
        List<Map<String, Object>> cands = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            if (a.sjs().contains(Rows.str(r, "sj_div", ""))) cands.add(r);
        }
        for (Map<String, Object> r : cands) {
            String id = Rows.str(r, "account_id");
            if (id != null && a.ids().contains(id)) return r;
        }
        Set<String> wanted = new java.util.HashSet<>();
        for (String n : a.names()) wanted.add(Rows.noSpace(n));
        for (Map<String, Object> r : cands) {
            if (wanted.contains(Rows.noSpace(Rows.str(r, "account_nm")))) return r;
        }
        return null;
    }

    record Picked(Map<String, Object> row, boolean fallback) {
    }

    static Picked pick(List<Map<String, Object>> rows, String key) {
        Map<String, Object> r = findRow(rows, key);
        if (r == null && FALLBACK.containsKey(key)) {
            return new Picked(findRow(rows, FALLBACK.get(key)), true);
        }
        return new Picked(r, false);
    }

    private static String firstRcept(List<Map<String, Object>> rows) {
        for (Map<String, Object> r : rows) {
            if (Rows.truthy(r.get("rcept_no"))) return Rows.str(r, "rcept_no");
        }
        return null;
    }

    /** 접수번호 앞 8자리(접수일)가 기준일 이전인지. 접수번호가 없으면(피어 주요계정) 확인하지 않는다. */
    private static boolean filedBy(List<Map<String, Object>> rows, LocalDate asOf) {
        String rno = firstRcept(rows);
        if (rno == null) return true;
        String head = rno.length() > 8 ? rno.substring(0, 8) : rno;
        return head.compareTo(asOf.format(DateTimeFormatter.BASIC_ISO_DATE)) <= 0;
    }

    // ───────────────────────── 수집 ─────────────────────────

    /** 원천에 연결하지 못해 재무를 받지 못했을 때 notes 앞머리. 화면은 이것으로 '데이터 없음'과 '연결 실패'를 가른다 */
    public static final String UNAVAILABLE_NOTE = "OpenDART에 연결하지 못해 재무를 받지 못함: ";

    public static boolean sourceUnavailable(List<String> notes) {
        return notes.stream().anyMatch(n -> n.startsWith(UNAVAILABLE_NOTE));
    }

    /** 최근 연간 재무, 그다음 해 최근 중간 재무, 시세. 실패는 notes로 남긴다. */
    public static Inputs gather(RadarSource source, Map<String, Object> company, LocalDate asOf) {
        String corp = Rows.str(company, "corp_code");
        List<String> notes = new ArrayList<>();
        Period annual = null;
        for (int y = asOf.getYear() - 1; y > asOf.getYear() - 5; y--) {   // 기준일 전년부터 거슬러 올라간다
            RadarSource.Financials f;
            try {
                f = source.financials(corp, y, "11011");
            } catch (SourceUnavailableException e) {   // 연결 실패는 '그해 재무 없음'이 아니다. 더 거슬러 올라가 봐야 똑같다
                notes.add(UNAVAILABLE_NOTE + e.getMessage());
                break;
            } catch (DataSourceException e) {
                continue;
            }
            if (filedBy(f.rows(), asOf)) {
                String rno = firstRcept(f.rows());
                annual = new Period(y, "11011", f.rows(), f.fsDiv(), rno == null ? "" : rno);
                break;
            }
        }
        Period interim = null;
        if (annual != null) {
            for (String code : INTERIM_ORDER) {
                RadarSource.Financials f;
                try {
                    f = source.financials(corp, annual.year() + 1, code);
                } catch (DataSourceException e) {
                    continue;
                }
                if (!filedBy(f.rows(), asOf)) continue;
                if (!f.fsDiv().equals(annual.fs())) {
                    notes.add((annual.year() + 1) + " " + Dart.REPRT.get(code).name() + " 재무가 " + f.fsDiv()
                            + "라 연간(" + annual.fs() + ")과 범위가 달라 TTM에 쓰지 않음");
                    continue;
                }
                String rno = firstRcept(f.rows());
                interim = new Period(annual.year() + 1, code, f.rows(), f.fsDiv(), rno == null ? "" : rno);
                break;
            }
        } else if (!sourceUnavailable(notes)) {
            notes.add("기준일 이전 사업보고서 재무 데이터를 찾지 못함");
        }
        String ymd = asOf.format(DateTimeFormatter.BASIC_ISO_DATE);
        List<Map<String, Object>> prices = new ArrayList<>();
        try {
            for (Map<String, Object> p : source.market(Rows.str(company, "stock_code", ""))) {
                if (Rows.str(p, "basDt", "").compareTo(ymd) <= 0) prices.add(p);
            }
        } catch (DataSourceException e) {
            prices = new ArrayList<>();
            notes.add("시세 조회 실패: " + e.getMessage());
        }
        if (prices.isEmpty()) {
            notes.add("시세 없음(공공데이터포털 키 미설정이거나 해당 종목 시세 없음)");
        }
        String msrc = null;
        if (!prices.isEmpty()) {
            msrc = "sample".equals(source.name()) ? "sample" : "data.go.kr";
        }
        prices.sort(Comparator.comparing(p -> Rows.str(p, "basDt", "")));
        return new Inputs(company, asOf.toString(), annual, interim, prices, msrc, notes);
    }

    // ───────────────────────── 계산 ─────────────────────────

    private record Cum(Long value, String field) {
    }

    /** 중간보고서 손익의 누적 금액과 쓴 필드. 1분기는 3개월이 곧 누적이라 누적 필드가 비어 있을 수 있다. */
    private static Cum cum(Map<String, Object> row, String reprtCode, boolean current) {
        if (row == null) return new Cum(null, "");
        String fAdd = current ? "thstrm_add_amount" : "frmtrm_add_amount";
        Long v = amount(row.get(fAdd));
        if (v != null) return new Cum(v, fAdd);
        if ("11013".equals(reprtCode)) {
            for (String f : current ? List.of("thstrm_amount") : List.of("frmtrm_q_amount", "frmtrm_amount")) {
                v = amount(row.get(f));
                if (v != null) return new Cum(v, f);
            }
        }
        return new Cum(null, fAdd);
    }

    private static List<String> notesOf(String first, String note) {
        List<String> out = new ArrayList<>();
        out.add(first);
        if (note != null) out.add(note);
        return out;
    }

    /** TTM Formula. 지배주주 계정은 연간·중간 양쪽에 다 있어야 쓰고, 아니면 둘 다 전체 계정으로 맞춘다. */
    private static Map<String, Object> ttm(String key, Period annual, Period interim) {
        String nm = NAMES.get(key);
        String use = key;
        boolean fallback = false;
        if (FALLBACK.containsKey(key)) {
            boolean hasA = findRow(annual.rows(), key) != null;
            boolean hasI = interim == null || findRow(interim.rows(), key) != null;
            if (!(hasA && hasI)) {
                use = FALLBACK.get(key);
                fallback = true;
            }
        }
        String note = fallback ? "대체 계정: 지배주주 계정이 없어 " + NAMES.get(use) + "(전체) 사용" : null;
        Map<String, Object> aRow = findRow(annual.rows(), use);
        Long aVal = aRow != null ? amount(aRow.get("thstrm_amount")) : null;
        Map<String, Object> aIn = inp("최근 연간(" + annual.year() + ")", aVal, "원",
                finSource(aRow, "thstrm_amount", null, annual.fs()), note);
        String fid = switch (key) {
            case "rev" -> "ttm_revenue";
            case "op" -> "ttm_op";
            default -> "ttm_ni_owner";
        };
        if (interim == null) {
            return formula(fid, nm + " TTM", "최근 연간 (연간 이후 중간보고서 없음)", List.of(aIn), aVal, "원",
                    aVal != null ? null : "연간 " + nm + " 값 없음",
                    notesOf("연간 이후 중간보고서가 없어 최근 연간 값을 그대로 씀", note), null);
        }
        String code = interim.reprtCode();
        Map<String, Object> iRow = findRow(interim.rows(), use);
        Cum c = cum(iRow, code, true);
        Cum p = cum(iRow, code, false);
        String rname = Dart.REPRT.get(code).name().replace("보고서", "");
        List<Map<String, Object>> inputs = List.of(aIn,
                inp("당해 " + rname + " 누적(" + interim.year() + ")", c.value(), "원", finSource(iRow, c.field(), null, interim.fs()), note),
                inp("전년 같은 " + rname + " 누적(" + (interim.year() - 1) + ")", p.value(), "원",
                        finSource(iRow, p.field(), null, interim.fs()), note));
        Long res = aVal == null || c.value() == null || p.value() == null ? null : aVal + c.value() - p.value();
        return formula(fid, nm + " TTM", "최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적", inputs, res, "원", null,
                notesOf("범위: " + interim.fs() + "(연간·중간 같은 범위)", note), null);
    }

    /** 다른 Formula의 결과를 다음 계산의 입력값으로. */
    private static List<Map<String, Object>> inputsOf(Map<String, Object> f) {
        List<Map<String, Object>> out = new ArrayList<>();
        out.add(inp((String) f.get("label"), f.get("result"), (String) f.get("unit"),
                src("계산", f.get("label") + " = " + f.get("expr"))));
        return out;
    }

    private static Map<String, Object> per(Map<String, Object> mc, String fid, String label, Map<String, Object> earnIn) {
        List<Map<String, Object>> ins = inputsOf(mc);
        ins.add(earnIn);
        Number e = (Number) earnIn.get("value");
        if (e != null && e.doubleValue() <= 0) {
            return formula(fid, label, "시가총액 ÷ 지배주주 순이익", ins, null, "배",
                    "지배주주 순이익이 0 이하라 PER을 계산하지 않음", null, null);
        }
        return formula(fid, label, "시가총액 ÷ 지배주주 순이익", ins, ratio((Number) mc.get("result"), e), "배", null, null, 2);
    }

    /** Valuation(§6.5). 연간 재무가 없으면 null. */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> fromInputs(Inputs vi) {
        Period annual = vi.annual();
        Period interim = vi.interim();
        if (annual == null) return null;
        List<String> notes = new ArrayList<>(vi.notes());
        List<Map<String, Object>> prices = vi.prices();
        Map<String, Object> last = prices.isEmpty() ? null : prices.get(prices.size() - 1);
        Map<String, Object> price = null;
        Map<String, Object> mc;
        if (last != null) {
            Long close = amount(last.get("clpr"));
            Long shares = amount(last.get("lstgStCnt"));
            Long cap = close != null && shares != null ? close * shares : null;
            String bas = Rows.str(last, "basDt");
            price = Rows.m("basDt", bas, "close", close, "listedShares", shares, "marketCap", cap);
            String itms = Rows.str(last, "itmsNm", "");
            Map<String, Object> pSrc = src("시세", (itms + " " + bas + " 종가").strip(), null, null, "clpr", null);
            Map<String, Object> sSrc = src("시세", (itms + " " + bas + " 상장주식수").strip(), null, null, "lstgStCnt", null);
            mc = formula("market_cap", "시가총액", "종가 × 상장주식수",
                    List.of(inp("종가", close, "원", pSrc), inp("상장주식수", shares, "주", sSrc)), cap, "원", null,
                    List.of("기준일 " + bas), null);
        } else {
            mc = formula("market_cap", "시가총액", "종가 × 상장주식수",
                    List.of(inp("종가", null, "원"), inp("상장주식수", null, "주")), null, "원", "시세 없음", null, null);
        }
        Map<String, Object> tRev = ttm("rev", annual, interim);
        Map<String, Object> tOp = ttm("op", annual, interim);
        Map<String, Object> tNi = ttm("ni_owner", annual, interim);

        String tNote = null;
        for (String n : (List<String>) tNi.get("notes")) {
            if (n.startsWith("대체 계정")) {
                tNote = n;
                break;
            }
        }
        Map<String, Object> perTtm = per(mc, "per_ttm", "PER(TTM)", inp((String) tNi.get("label"), tNi.get("result"), "원",
                src("계산", tNi.get("label") + " = " + tNi.get("expr")), tNote));
        Picked a = pick(annual.rows(), "ni_owner");
        Long aNi = a.row() != null ? amount(a.row().get("thstrm_amount")) : null;
        String aNote = a.fallback() ? "대체 계정: 지배주주 계정이 없어 " + NAMES.get("ni") + "(전체) 사용" : null;
        Map<String, Object> perAnnual = per(mc, "per_annual", "PER(연간 " + annual.year() + ")",
                inp("지배주주 순이익(" + annual.year() + ")", aNi, "원", finSource(a.row(), "thstrm_amount", null, annual.fs()), aNote));

        // PBR: 가장 최근 기말(중간보고서가 있으면 그 기말) 지배주주 자본
        Period base = interim != null ? interim : annual;
        Picked e = pick(base.rows(), "equity_owner");
        Long eq = e.row() != null ? amount(e.row().get("thstrm_amount")) : null;
        String eNote = e.fallback() ? "대체 계정: 지배주주 계정이 없어 " + NAMES.get("equity") + "(전체) 사용" : null;
        String period = base.year() + " " + (interim != null
                ? Dart.REPRT.get(base.reprtCode()).name().replace("보고서", "") + "말" : "기말");
        List<Map<String, Object>> pbrIn = inputsOf(mc);
        pbrIn.add(inp("지배주주 자본(" + period + ")", eq, "원", finSource(e.row(), "thstrm_amount", null, base.fs()), eNote));
        Map<String, Object> pbr;
        if (eq != null && eq <= 0) {
            pbr = formula("pbr", "PBR", "시가총액 ÷ 지배주주 자본", pbrIn, null, "배",
                    "지배주주 자본이 0 이하라 PBR을 계산하지 않음", null, null);
        } else {
            pbr = formula("pbr", "PBR", "시가총액 ÷ 지배주주 자본", pbrIn, ratio((Number) mc.get("result"), eq), "배", null, null, 2);
        }

        notes.add("PER·PBR은 계산식과 입력값만 보여 주며 해석하지 않습니다.");
        if (interim == null) {
            notes.add((annual.year() + 1) + "년 중간보고서 재무가 없어 TTM은 " + annual.year() + "년 연간 값과 같음");
        }
        List<Map<String, Object>> series = new ArrayList<>();
        for (Map<String, Object> p : prices) {
            Long c = amount(p.get("clpr"));
            if (c != null) series.add(Rows.m("d", p.get("basDt"), "c", c));
        }
        String asOf = null;
        if (last != null) {
            String b = Rows.str(last, "basDt");
            asOf = b.substring(0, 4) + "-" + b.substring(4, 6) + "-" + b.substring(6);
        }
        return Rows.m(
                "asOf", asOf,
                "marketSource", vi.marketSource(),
                "fsDiv", annual.fs(),
                "annual", Rows.m("year", annual.year(), "rceptNo", annual.rceptNo()),
                "interim", interim == null ? null
                        : Rows.m("year", interim.year(), "reprtCode", interim.reprtCode(), "rceptNo", interim.rceptNo()),
                "price", price,
                "prices", series,
                "metrics", List.of(mc, tRev, tOp, tNi, perTtm, perAnnual, pbr),
                "notes", notes);
    }

    public static Map<String, Object> compute(RadarSource source, Map<String, Object> company, LocalDate asOf) {
        return fromInputs(gather(source, company, asOf));
    }

    /** Valuation에서 지표 하나의 결과값(없으면 null). */
    @SuppressWarnings("unchecked")
    public static Number metric(Map<String, Object> val, String fid) {
        if (val == null) return null;
        for (Map<String, Object> m : (List<Map<String, Object>>) val.get("metrics")) {
            if (fid.equals(m.get("id"))) return (Number) m.get("result");
        }
        return null;
    }
}
