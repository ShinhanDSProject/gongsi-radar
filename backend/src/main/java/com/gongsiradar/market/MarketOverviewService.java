package com.gongsiradar.market;

import com.gongsiradar.data.Dart;
import com.gongsiradar.data.DataSourceException;
import com.gongsiradar.data.RadarSource;
import com.gongsiradar.data.Rows;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static com.gongsiradar.radar.Formulas.amount;
import static com.gongsiradar.radar.Formulas.pyRound;
import static com.gongsiradar.radar.Formulas.src;

/**
 * 시장 화면(알파인더 /market 참고): 지수 추이 · 시가총액 추이 · 업종 지도(KSIC) · 최근 정기보고서.
 * 계약은 CONTRACT §9 MarketOverview. 파이썬 {@code radar/market.py}를 옮겼다(골든 테스트로 같은 결과를 확인한다).
 * <ul>
 *   <li>시가총액 추이: 날짜별 추적 종목 시가총액(mrktTotAmt) 합계. 그 날 시세가 없는 종목은 빼지 않고 직전 값을 이어 쓴다
 *       (시세가 하루 빠졌다고 합계가 꺼지면 시장이 폭락한 것처럼 보인다)</li>
 *   <li>지수 추이: 공식 지수(공공데이터포털 지수시세)가 있으면 그 값을, 없으면 추적 종목 시가총액으로 만든
 *       <b>대체 지수</b>(기준일 = 1,000)를 쓰고 kind="proxy"로 분명히 표시한다. 대체 지수를 코스피라고 부르지 않는다</li>
 *   <li>업종 지도: KSIC 코드 앞 두 자리(중분류) → 대분류 문자. 면적 = 시가총액. 색은 등락률이 아니다</li>
 *   <li>기간 변화: 최신일에서 거꾸로 7일·1개월·1년 이내의 마지막 거래일과 비교. 그만큼 데이터가 없으면 계산하지 않는다</li>
 * </ul>
 */
@Service
public class MarketOverviewService {

    static final String[][] MARKETS = {{"ALL", "전체"}, {"KOSPI", "유가"}, {"KOSDAQ", "코스닥"}, {"KONEX", "코넥스"}};
    static final Object[][] PERIODS = {{"1D", "전일", null}, {"1W", "1주", 7}, {"1M", "1개월", 31}, {"1Y", "1년", 365}};
    static final Object[][] RANGES = {{"1Y", 360}, {"3Y", 3 * 365 - 10}, {"5Y", 5 * 365 - 10}};
    static final String[][] INDEX_NAMES = {{"KOSPI", "코스피"}, {"KOSDAQ", "코스닥"}};
    static final double PROXY_BASE = 1000.0;
    static final int INDUTY_LOOKUP_LIMIT = 300;   // 실데이터에서 업종 코드(기업개황)를 불러올 상위 종목 수

    /** KSIC 11 대분류(중분류 범위) */
    static final Object[][] KSIC_SECTIONS = {
            {"A", 1, 3, "농업, 임업 및 어업"}, {"B", 5, 8, "광업"}, {"C", 10, 34, "제조업"},
            {"D", 35, 35, "전기, 가스, 증기 및 공기조절 공급업"}, {"E", 36, 39, "수도, 하수 및 폐기물 처리, 원료 재생업"},
            {"F", 41, 42, "건설업"}, {"G", 45, 47, "도매 및 소매업"}, {"H", 49, 52, "운수 및 창고업"},
            {"I", 55, 56, "숙박 및 음식점업"}, {"J", 58, 63, "정보통신업"}, {"K", 64, 66, "금융 및 보험업"},
            {"L", 68, 68, "부동산업"}, {"M", 70, 73, "전문, 과학 및 기술 서비스업"},
            {"N", 74, 76, "사업시설 관리, 사업 지원 및 임대 서비스업"}, {"O", 84, 84, "공공 행정, 국방 및 사회보장 행정"},
            {"P", 85, 85, "교육 서비스업"}, {"Q", 86, 87, "보건업 및 사회복지 서비스업"},
            {"R", 90, 91, "예술, 스포츠 및 여가관련 서비스업"}, {"S", 94, 96, "협회 및 단체, 수리 및 기타 개인 서비스업"},
            {"T", 97, 98, "가구 내 고용활동 및 달리 분류되지 않은 자가 소비 생산활동"}, {"U", 99, 99, "국제 및 외국기관"},
    };
    static final Map<String, String> KSIC_DIVISIONS = new HashMap<>();

    static {
        String[] kv = {
                "10", "식료품 제조업", "11", "음료 제조업", "12", "담배 제조업", "13", "섬유제품 제조업", "14", "의복 제조업",
                "15", "가죽·가방·신발 제조업", "16", "목재 및 나무제품 제조업", "17", "펄프·종이 제조업", "18", "인쇄 및 기록매체 복제업",
                "19", "코크스·석유정제품 제조업", "20", "화학물질 및 화학제품 제조업", "21", "의료용 물질 및 의약품 제조업",
                "22", "고무 및 플라스틱제품 제조업", "23", "비금속 광물제품 제조업", "24", "1차 금속 제조업", "25", "금속 가공제품 제조업",
                "26", "전자부품·컴퓨터·영상·음향·통신장비 제조업", "27", "의료·정밀·광학 기기 및 시계 제조업", "28", "전기장비 제조업",
                "29", "기타 기계 및 장비 제조업", "30", "자동차 및 트레일러 제조업", "31", "기타 운송장비 제조업", "32", "가구 제조업",
                "33", "기타 제품 제조업", "34", "산업용 기계 및 장비 수리업", "35", "전기, 가스, 증기 및 공기조절 공급업",
                "36", "수도업", "37", "하수·폐수 및 분뇨 처리업", "38", "폐기물 수집·처리 및 원료 재생업", "39", "환경 정화 및 복원업",
                "41", "종합 건설업", "42", "전문직별 공사업", "45", "자동차 및 부품 판매업", "46", "도매 및 상품 중개업",
                "47", "소매업(자동차 제외)", "49", "육상 운송 및 파이프라인 운송업", "50", "수상 운송업", "51", "항공 운송업",
                "52", "창고 및 운송관련 서비스업", "55", "숙박업", "56", "음식점 및 주점업", "58", "출판업",
                "59", "영상·오디오 기록물 제작 및 배급업", "60", "방송업", "61", "우편 및 통신업",
                "62", "컴퓨터 프로그래밍·시스템 통합 및 관리업", "63", "정보서비스업", "64", "금융업", "65", "보험 및 연금업",
                "66", "금융 및 보험관련 서비스업", "68", "부동산업", "70", "연구개발업", "71", "전문 서비스업",
                "72", "건축기술·엔지니어링 및 기타 과학기술 서비스업", "73", "기타 전문·과학 및 기술 서비스업",
                "74", "사업시설 관리 및 조경 서비스업", "75", "사업 지원 서비스업", "76", "임대업(부동산 제외)", "85", "교육 서비스업",
                "86", "보건업", "87", "사회복지 서비스업", "90", "창작·예술 및 여가관련 서비스업", "91", "스포츠 및 오락관련 서비스업",
        };
        for (int i = 0; i < kv.length; i += 2) KSIC_DIVISIONS.put(kv[i], kv[i + 1]);
    }

    static final String UNKNOWN_CODE = "?";
    static final String UNKNOWN_NAME = "업종 미확인";
    private static final Pattern DIV2 = Pattern.compile("^\\s*(\\d{2})");

    private final RadarSource source;

    public MarketOverviewService(RadarSource source) {
        this.source = source;
    }

    // ───────────────────────── KSIC ─────────────────────────

    /** KSIC 코드 → (대분류 문자, 이름). 숫자 앞 두 자리(중분류)로 판정한다. */
    static String[] ksicSection(String code) {
        Matcher m = DIV2.matcher(code == null ? "" : code);
        if (!m.find()) return new String[]{UNKNOWN_CODE, UNKNOWN_NAME};
        int div = Integer.parseInt(m.group(1));
        for (Object[] s : KSIC_SECTIONS) {
            if ((Integer) s[1] <= div && div <= (Integer) s[2]) return new String[]{(String) s[0], (String) s[3]};
        }
        return new String[]{UNKNOWN_CODE, UNKNOWN_NAME};
    }

    static String[] ksicDivision(String code) {
        Matcher m = DIV2.matcher(code == null ? "" : code);
        if (!m.find()) return new String[]{"??", UNKNOWN_NAME};
        return new String[]{m.group(1), KSIC_DIVISIONS.getOrDefault(m.group(1), "중분류 " + m.group(1))};
    }

    static String iso(String bas) {
        return bas.substring(0, 4) + "-" + bas.substring(4, 6) + "-" + bas.substring(6);
    }

    static Long cap(Map<String, Object> row) {
        Long cap = amount(row.get("mrktTotAmt"));
        Long c = amount(row.get("clpr"));
        Long s = amount(row.get("lstgStCnt"));
        if (cap == null && c != null && c != 0 && s != null && s != 0) {
            cap = c * s;
        }
        return cap;
    }

    private static Map<String, Object> latestRow(List<Map<String, Object>> rows) {
        Map<String, Object> last = rows.get(0);
        for (Map<String, Object> r : rows) {
            if (Rows.str(r, "basDt", "").compareTo(Rows.str(last, "basDt", "")) > 0) last = r;
        }
        return last;
    }

    // ───────────────────────── 기간 변화 ─────────────────────────

    /** series: [{d: 'YYYY-MM-DD', v}] 오래된 것 → 최신. delta 단위는 series 값 단위(정수 시리즈면 정수). */
    static List<Map<String, Object>> periodChanges(List<Map<String, Object>> series) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (series.isEmpty()) {
            for (Object[] p : PERIODS) {
                out.add(Rows.m("period", p[0], "label", p[1], "pct", null, "delta", null, "from", null, "to", null,
                        "reason", "데이터 없음"));
            }
            return out;
        }
        Map<String, Object> last = series.get(series.size() - 1);
        LocalDate to = LocalDate.parse((String) last.get("d"));
        for (Object[] p : PERIODS) {
            Map<String, Object> base = null;
            if (p[2] == null) {
                base = series.size() >= 2 ? series.get(series.size() - 2) : null;
            } else {
                LocalDate target = to.minusDays((Integer) p[2]);
                for (int i = series.size() - 1; i >= 0; i--) {
                    if (!LocalDate.parse((String) series.get(i).get("d")).isAfter(target)) {
                        base = series.get(i);
                        break;
                    }
                }
                // 목표일과 너무 멀리 떨어진 값(데이터 시작점이 목표보다 한참 뒤)은 쓰지 않는다
                if (base != null && LocalDate.parse((String) base.get("d")).isBefore(target.minusDays(10))) {
                    base = null;
                }
            }
            Number bv = base == null ? null : (Number) base.get("v");
            if (bv == null || bv.doubleValue() == 0) {
                out.add(Rows.m("period", p[0], "label", p[1], "pct", null, "delta", null, "from", null,
                        "to", last.get("d"), "reason", "기간 데이터 부족"));
                continue;
            }
            Number lv = (Number) last.get("v");
            Number delta;
            double d;
            if (lv instanceof Long && bv instanceof Long) {
                long dl = lv.longValue() - bv.longValue();
                delta = dl;
                d = dl;
            } else {
                d = lv.doubleValue() - bv.doubleValue();
                delta = pyRound(d, 2);
            }
            out.add(Rows.m("period", p[0], "label", p[1], "pct", pyRound(d / Math.abs(bv.doubleValue()) * 100, 2),
                    "delta", delta, "from", base.get("d"), "to", last.get("d")));
        }
        return out;
    }

    static List<String> availableRanges(List<Map<String, Object>> series) {
        if (series.size() < 2) return new ArrayList<>();
        long span = ChronoUnit.DAYS.between(LocalDate.parse((String) series.get(0).get("d")),
                LocalDate.parse((String) series.get(series.size() - 1).get("d")));
        List<String> out = new ArrayList<>();
        for (Object[] r : RANGES) {
            if (span >= (Integer) r[1]) out.add((String) r[0]);
        }
        if (out.isEmpty()) out.add("1Y");
        return out;
    }

    // ───────────────────────── 시가총액 ─────────────────────────

    /** 날짜별 시가총액 합계. 그 날 시세가 빠진 종목은 직전 값을 이어 쓴다(처음 나타나기 전 날짜는 0). */
    static List<Map<String, Object>> capSeries(Map<String, List<Map<String, Object>>> history, List<String> codes) {
        Map<String, Map<String, Long>> byCode = new LinkedHashMap<>();
        TreeSet<String> days = new TreeSet<>();
        for (String c : codes) {
            Map<String, Long> m = new HashMap<>();
            for (Map<String, Object> r : history.getOrDefault(c, List.of())) {
                Long v = cap(r);
                if (v != null && Rows.truthy(r.get("basDt"))) m.put(Rows.str(r, "basDt"), v);
            }
            if (!m.isEmpty()) {
                byCode.put(c, m);
                days.addAll(m.keySet());
            }
        }
        Map<String, Long> last = new HashMap<>();
        List<Map<String, Object>> out = new ArrayList<>();
        for (String d : days) {
            for (Map.Entry<String, Map<String, Long>> e : byCode.entrySet()) {
                Long v = e.getValue().get(d);
                if (v != null) last.put(e.getKey(), v);
            }
            long sum = 0;
            for (long v : last.values()) sum += v;
            out.add(Rows.m("d", iso(d), "v", sum));
        }
        return out;
    }

    /** 시가총액 합계를 첫날 = 1,000으로 맞춘 대체 지수. 종목 구성이 바뀌면 왜곡된다(공식 지수는 이를 보정한다). */
    static List<Map<String, Object>> proxyIndex(List<Map<String, Object>> series) {
        if (series.isEmpty() || ((Number) series.get(0).get("v")).doubleValue() == 0) return new ArrayList<>();
        double base = ((Number) series.get(0).get("v")).doubleValue();
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> p : series) {
            out.add(Rows.m("d", p.get("d"), "v", pyRound(((Number) p.get("v")).doubleValue() / base * PROXY_BASE, 2)));
        }
        return out;
    }

    // ───────────────────────── 업종 지도 ─────────────────────────

    private static Map<String, Object> node(String id, String name, String level, String code) {
        return Rows.m("id", id, "name", name, "level", level, "code", code, "value", 0L, "count", 0, "share", 0.0,
                "children", new ArrayList<Map<String, Object>>());
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> children(Map<String, Object> n) {
        return (List<Map<String, Object>>) n.get("children");
    }

    /** items: [{corp_code, corp_name, stock_code, induty_code, cap}] → 대분류 → 중분류 → 기업 트리. */
    static Map<String, Object> sectorTree(List<Map<String, Object>> items) {
        Map<String, Object> root = node("root", "전체 업종", "root", null);
        Map<String, Map<String, Object>> sections = new LinkedHashMap<>();
        for (Map<String, Object> it : items) {
            Long cap = (Long) it.get("cap");
            if (cap == null || cap == 0) continue;
            String induty = Rows.str(it, "induty_code");
            String[] sec = ksicSection(induty);
            Map<String, Object> s = sections.computeIfAbsent(sec[0], k -> node("S-" + sec[0],
                    !sec[0].equals(UNKNOWN_CODE) ? sec[0] + " " + sec[1] : sec[1], "section",
                    sec[0].equals(UNKNOWN_CODE) ? null : sec[0]));
            String[] dv = ksicDivision(induty);
            Map<String, Object> div = null;
            for (Map<String, Object> d : children(s)) {
                if (java.util.Objects.equals(d.get("code"), dv[0])) {
                    div = d;
                    break;
                }
            }
            if (div == null) {
                div = node("D-" + dv[0], !dv[0].equals("??") ? dv[0] + " " + dv[1] : dv[1], "division",
                        dv[0].equals("??") ? null : dv[0]);
                children(s).add(div);
            }
            children(div).add(Rows.m("id", "C-" + it.get("corp_code"), "name", it.get("corp_name"), "level", "company",
                    "code", it.get("stock_code"), "value", cap, "count", 1, "share", 0.0, "corpCode", it.get("corp_code")));
        }
        root.put("children", new ArrayList<>(sections.values()));
        total(root);
        root.put("share", 100.0);
        return root;
    }

    private static void total(Map<String, Object> n) {
        if ("company".equals(n.get("level"))) return;
        List<Map<String, Object>> ch = children(n);
        for (Map<String, Object> c : ch) total(c);
        long value = 0;
        int count = 0;
        for (Map<String, Object> c : ch) {
            value += ((Number) c.get("value")).longValue();
            count += ((Number) c.get("count")).intValue();
        }
        n.put("value", value);
        n.put("count", count);
        ch.sort(Comparator.comparingLong((Map<String, Object> c) -> -((Number) c.get("value")).longValue()));
        for (Map<String, Object> c : ch) {
            c.put("share", value != 0 ? pyRound(((Number) c.get("value")).doubleValue() / value * 100, 2) : 0.0);
        }
    }

    // ───────────────────────── 최근 정기보고서 ─────────────────────────

    static List<Map<String, Object>> recentTable(List<Map<String, Object>> filings, Map<String, Long> caps,
                                                 Map<String, String> corpMarket, String market, int limit) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> f : filings) {
            if (!"ALL".equals(market) && !market.equals(corpMarket.get(Rows.str(f, "corp_code")))) continue;
            String nm = Rows.str(f, "report_nm", "");
            String stock = Rows.str(f, "stock_code", "");
            out.add(Rows.m("rceptNo", f.get("rcept_no"), "rceptDt", iso(Rows.str(f, "rcept_dt")), "corpCode", f.get("corp_code"),
                    "corpName", f.get("corp_name"), "stockCode", Rows.orNull(stock), "reportNm", nm,
                    "reprtCode", f.get("reprt_code"), "bsnsYear", f.get("bsns_year"), "marketCap", caps.get(stock),
                    "isCorrection", nm.contains("정정") || Rows.str(f, "rm", "").contains("정"),
                    "hasDocument", Rows.truthy(f.get("hasDocument")), "url", Dart.dartUrl(Rows.str(f, "rcept_no"))));
            if (out.size() >= limit) break;
        }
        return out;
    }

    // ───────────────────────── 종합 ─────────────────────────

    private static String marketOf(Map<String, Object> c, List<Map<String, Object>> rows) {
        if (c != null && Rows.truthy(c.get("market"))) return Rows.str(c, "market");
        String m = rows.isEmpty() ? "" : Rows.str(latestRow(rows), "mrktCtg", "").toUpperCase(Locale.ROOT);
        return switch (m) {
            case "KOSPI", "KOSDAQ", "KONEX" -> m;
            default -> null;
        };
    }

    public Map<String, Object> overview(String market) {
        return overview(source, market);
    }

    /** MarketOverview. market은 ALL·KOSPI·KOSDAQ·KONEX(대소문자 무시). 그 밖이면 IllegalArgumentException. */
    public static Map<String, Object> overview(RadarSource source, String market) {
        market = (market == null || market.isEmpty() ? "ALL" : market).toUpperCase(Locale.ROOT);
        boolean known = false;
        for (String[] m : MARKETS) known |= m[0].equals(market);
        if (!known) throw new IllegalArgumentException("market은 ALL, KOSPI, KOSDAQ, KONEX 중 하나");
        boolean sample = "sample".equals(source.name());
        List<String> notes = new ArrayList<>();
        Map<String, List<Map<String, Object>>> history = source.marketHistory();
        Map<String, Map<String, Object>> corps = new LinkedHashMap<>();
        for (Map<String, Object> c : source.companies()) {
            if (Rows.truthy(c.get("stock_code"))) corps.put(Rows.str(c, "stock_code"), c);
        }
        if (history.isEmpty()) {
            notes.add("시세 데이터가 없습니다. 실데이터는 DATA_GO_KR_API_KEY(공공데이터포털 주식시세정보)가 필요합니다.");
        }

        // 종목별 최신 시가총액·시장 구분
        Map<String, Long> latest = new LinkedHashMap<>();
        Map<String, String> mkt = new HashMap<>();
        Map<String, String> names = new HashMap<>();
        TreeSet<String> allDays = new TreeSet<>();
        for (Map.Entry<String, List<Map<String, Object>>> e : history.entrySet()) {
            List<Map<String, Object>> rows = e.getValue();
            for (Map<String, Object> r : rows) {
                if (Rows.truthy(r.get("basDt"))) allDays.add(Rows.str(r, "basDt"));
            }
            if (rows.isEmpty()) continue;
            String code = e.getKey();
            Map<String, Object> last = latestRow(rows);
            String itms = Rows.str(last, "itmsNm");
            names.put(code, itms != null && !itms.isEmpty() ? itms : code);   // 목록에 없는 종목(우선주 등)은 시세의 종목명
            Long cp = cap(last);
            if (cp != null) latest.put(code, cp);
            mkt.put(code, marketOf(corps.get(code), rows));
        }
        String asOf = allDays.isEmpty() ? null : iso(allDays.last());

        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String[] m : MARKETS) counts.put(m[0], 0);
        for (String code : latest.keySet()) {
            counts.merge("ALL", 1, Integer::sum);
            String mk = mkt.get(code);
            if (mk != null && counts.containsKey(mk)) counts.merge(mk, 1, Integer::sum);
        }
        List<String> selected = new ArrayList<>();
        for (String c : latest.keySet()) {
            if ("ALL".equals(market) || market.equals(mkt.get(c))) selected.add(c);
        }

        // 시가총액 추이
        List<Map<String, Object>> series = capSeries(history, selected);
        List<String> ranges = availableRanges(series);
        String rangeNote = null;
        if (!ranges.contains("5Y")) {
            rangeNote = (sample ? "샘플 시세는 1년치입니다." : "받아 둔 시세가 " + series.size() + "개 거래일분입니다.")
                    + " 더 긴 기간은 데이터가 쌓이면 열립니다.";
        }
        Map<String, Object> priceSrc = src("시세", "공공데이터포털 금융위원회_주식시세정보(getStockPriceInfo)" + (sample ? " · 가상 샘플" : ""));
        Map<String, Object> capitalization = Rows.m("total", series.isEmpty() ? null : series.get(series.size() - 1).get("v"),
                "series", series, "changes", periodChanges(series), "availableRanges", ranges, "rangeNote", rangeNote,
                "source", priceSrc);

        // 지수 추이(시장 필터와 무관)
        List<Map<String, Object>> indices = new ArrayList<>();
        for (String[] idx : INDEX_NAMES) {
            String code = idx[0], name = idx[1];
            List<Map<String, Object>> official = new ArrayList<>();
            try {
                official = source.indexSeries(name);
            } catch (DataSourceException e) {
                notes.add(name + " 공식 지수를 받지 못해 대체 지수를 씁니다: " + e.getMessage());
            }
            List<Map<String, Object>> ser;
            String kind, note;
            Map<String, Object> isrc;
            if (!official.isEmpty()) {
                ser = new ArrayList<>();
                for (Map<String, Object> r : official) {
                    if (Rows.truthy(r.get("basDt")) && Rows.truthy(r.get("clpr"))) {
                        ser.add(Rows.m("d", iso(Rows.str(r, "basDt")),
                                "v", Double.parseDouble(Rows.str(r, "clpr").replace(",", ""))));
                    }
                }
                ser.sort(Comparator.comparing(p -> (String) p.get("d")));
                kind = "official";
                note = name + " 일별 종가";
                isrc = src("시세", "공공데이터포털 금융위원회_지수시세정보(getStockMarketIndex)");
            } else {
                List<String> members = new ArrayList<>();
                for (String c : latest.keySet()) {
                    if (code.equals(mkt.get(c))) members.add(c);
                }
                ser = proxyIndex(capSeries(history, members));
                kind = "proxy";
                note = "공식 " + name + " 지수가 아닙니다. 추적 중인 " + name + " 상장 " + members.size()
                        + "개사의 시가총액 합계를 첫날 = 1,000으로 맞춘 대체 지수입니다(지수시세 키 DATA_GO_KR_API_KEY가 있으면 공식 지수로 바뀝니다).";
                isrc = src("계산", "추적 기업 시가총액 합계 ÷ 기준일 합계 × 1,000");
            }
            Map<String, Object> lastP = ser.isEmpty() ? null : ser.get(ser.size() - 1);
            indices.add(Rows.m("code", code, "name", "official".equals(kind) ? name : name + "(대체)", "kind", kind,
                    "last", lastP == null ? null : lastP.get("v"), "asOf", lastP == null ? null : lastP.get("d"),
                    "series", ser, "changes", periodChanges(ser), "availableRanges", availableRanges(ser),
                    "note", note, "source", isrc));
        }

        // 업종 지도: 업종 코드가 목록에 없으면(실데이터) 시가총액 상위만 기업개황에서 불러온다
        List<Map<String, Object>> items = new ArrayList<>();
        int lookups = 0;
        List<String> bySize = new ArrayList<>(selected);
        bySize.sort(Comparator.comparingLong(c -> -latest.get(c)));
        for (String code : bySize) {
            Map<String, Object> c = corps.get(code);
            if (c == null) {
                c = Rows.m("corp_code", code, "corp_name", names.getOrDefault(code, code), "stock_code", code);
            }
            String induty = Rows.str(c, "induty_code");
            if ((induty == null || induty.isEmpty()) && lookups < INDUTY_LOOKUP_LIMIT && !code.equals(c.get("corp_code"))) {
                lookups++;
                induty = source.indutyCode(Rows.str(c, "corp_code"));
            }
            items.add(Rows.m("corp_code", c.containsKey("corp_code") ? c.get("corp_code") : code,
                    "corp_name", c.containsKey("corp_name") ? c.get("corp_name") : code,
                    "stock_code", code, "induty_code", induty, "cap", latest.get(code)));
        }
        Map<String, Object> tree = sectorTree(items);
        if (children(tree).stream().anyMatch(s -> s.get("code") == null)) {
            notes.add("업종 코드를 확인하지 못한 기업은 '" + UNKNOWN_NAME + "'으로 묶었습니다"
                    + (sample ? "" : "(실데이터는 시가총액 상위 " + INDUTY_LOOKUP_LIMIT + "개사만 기업개황에서 조회)") + ".");
        }

        // 최근 정기보고서
        List<Map<String, Object>> filings;
        try {
            filings = source.recentFilings();
        } catch (DataSourceException e) {
            filings = List.of();
            notes.add("최근 정기보고서를 받지 못했습니다: " + e.getMessage());
        }
        Map<String, String> corpMarket = new HashMap<>();
        for (Map.Entry<String, Map<String, Object>> e : corps.entrySet()) {
            String m = mkt.get(e.getKey());
            corpMarket.put(Rows.str(e.getValue(), "corp_code"), m != null && !m.isEmpty() ? m : Rows.str(e.getValue(), "market"));
        }
        List<Map<String, Object>> recent = recentTable(filings, latest, corpMarket, market, 30);

        // 새로 확인한 기업(적재 DB가 있을 때만). 첫 적재일에 들어온 회사는 신규가 아니다
        boolean ingested = source.ingested();
        List<Map<String, Object>> newRows = new ArrayList<>();
        if (ingested) {
            for (Map<String, Object> c : source.newListings(30)) {
                String code = Rows.str(c, "stock_code", "");
                String m = Rows.str(c, "market");
                newRows.add(Rows.m("corpCode", c.get("corp_code"), "corpName", c.get("corp_name"),
                        "stockCode", Rows.orNull(code), "market", m != null && !m.isEmpty() ? m : mkt.get(code),
                        "firstSeen", String.valueOf(c.get("first_seen")), "marketCap", latest.get(code)));
            }
        }
        String newNote = ingested ? "일일 수집에서 처음 확인한 기업입니다. 확인일은 공식 상장일과 다를 수 있습니다."
                : "일일 수집(적재 DB)이 켜져 있을 때만 표시합니다.";

        String universe = sample ? "추적 기업 " + counts.get("ALL") + "개사(가상 샘플)"
                : String.format("상장 종목 %,d개", counts.get("ALL"));
        notes.add("시가총액은 종목별 시가총액(mrktTotAmt)의 합계입니다"
                + (sample ? "" : "(보통주·우선주 등 상장 종목을 각각 더함)") + ". 투자 판단 자료가 아닙니다.");
        List<Map<String, Object>> markets = new ArrayList<>();
        for (String[] m : MARKETS) markets.add(Rows.m("code", m[0], "label", m[1], "count", counts.get(m[0])));
        return Rows.m("asOf", asOf, "market", market, "markets", markets, "universeNote", universe, "sample", sample,
                "capitalization", capitalization, "indices", indices, "sectors", tree, "recentFilings", recent,
                "newListings", newRows, "newListingsNote", newNote, "ingested", ingested, "notes", notes);
    }
}
