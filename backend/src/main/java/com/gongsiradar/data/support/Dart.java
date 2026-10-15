package com.gongsiradar.data.support;

import com.gongsiradar.data.source.DataSourceException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** OpenDART 공통 규칙: 보고서 코드, 원문 링크, 보고서명 해석, 응답 행 꺼내기(파이썬 sources.py 상단 함수들). */
public final class Dart {

    private Dart() {
    }

    public record ReprtInfo(String name, String detail, String mm) {
    }

    /** 보고서 코드 → (이름, 공시 상세유형, 결산월) */
    public static final Map<String, ReprtInfo> REPRT = new LinkedHashMap<>();

    static {
        REPRT.put("11011", new ReprtInfo("사업보고서", "A001", "12"));
        REPRT.put("11012", new ReprtInfo("반기보고서", "A002", "06"));
        REPRT.put("11013", new ReprtInfo("1분기보고서", "A003", "03"));
        REPRT.put("11014", new ReprtInfo("3분기보고서", "A003", "09"));
    }

    public static ReprtInfo reprt(String code) {
        ReprtInfo info = REPRT.get(code);
        if (info == null) {
            throw new DataSourceException("지원하지 않는 보고서 코드입니다: " + code);
        }
        return info;
    }

    public static String dartUrl(String rceptNo) {
        return "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rceptNo;
    }

    private static final Pattern RNM = Pattern.compile("\\((\\d{4})\\.(\\d{2})\\)");

    public record Kind(String code, Integer year) {
    }

    /** '반기보고서 (2026.06)' → (11012, 2026). 정기보고서가 아니면 (null, null). */
    public static Kind reportKind(String reportNm) {
        String nm = reportNm == null ? "" : reportNm;
        Matcher m = RNM.matcher(nm);
        if (!m.find()) {
            return new Kind(null, null);
        }
        for (Map.Entry<String, ReprtInfo> e : REPRT.entrySet()) {
            if (nm.contains(e.getValue().name()) && e.getValue().mm().equals(m.group(2))) {
                return new Kind(e.getKey(), Integer.parseInt(m.group(1)));
            }
        }
        return new Kind(null, null);
    }

    /** list.json 행 → 정기보고서 행. 정기보고서가 아니면 null. */
    public static Map<String, Object> filingRow(Map<String, Object> r, boolean hasDoc) {
        Kind k = reportKind(Rows.str(r, "report_nm", ""));
        if (k.code() == null) {
            return null;
        }
        return Rows.m("rcept_no", r.get("rcept_no"), "report_nm", r.get("report_nm"), "rcept_dt", r.get("rcept_dt"),
                "reprt_code", k.code(), "bsns_year", k.year(), "hasDocument", hasDoc);
    }

    /** 정상(000) 응답의 list. 그 밖(013 데이터 없음 등)은 빈 목록. */
    public static List<Map<String, Object>> rows(Map<String, Object> d) {
        return "000".equals(Rows.str(d, "status")) ? Rows.list(d.get("list")) : List.of();
    }

    /** 지배구조 세 응답을 하나로. 접수번호는 처음 나오는 행의 것. */
    public static Map<String, Object> gov(List<Map<String, Object>> sh, List<Map<String, Object>> ex,
                                          List<Map<String, Object>> inv) {
        String rno = null;
        List<Map<String, Object>> all = new ArrayList<>(sh);
        all.addAll(ex);
        all.addAll(inv);
        for (Map<String, Object> r : all) {
            if (Rows.truthy(r.get("rcept_no"))) {
                rno = Rows.str(r, "rcept_no");
                break;
            }
        }
        return Rows.m("shareholders", sh, "executives", ex, "investments", inv, "rcept_no", rno);
    }

    /** 공공데이터포털 응답의 items.item. 한 건이면 객체로 오므로 목록으로 맞춘다. */
    public static List<Map<String, Object>> items(Map<String, Object> d) {
        Map<String, Object> body = Rows.map(Rows.map(d.get("response")).get("body"));
        Object item = Rows.map(body.get("items")).get("item");
        if (item instanceof Map<?, ?>) {
            return new ArrayList<>(List.of(Rows.map(item)));
        }
        return new ArrayList<>(Rows.list(item));
    }
}
