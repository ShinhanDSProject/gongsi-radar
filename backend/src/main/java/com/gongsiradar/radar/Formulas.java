package com.gongsiradar.radar;

import com.gongsiradar.data.Dart;
import com.gongsiradar.data.Rows;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 계산식·출처(Formula·Source, CONTRACT §6.2)와 금액 해석. 파이썬 {@code radar/formula.py}·{@code financials.amount}를 옮겼다.
 * <p>
 * 원칙
 * <ul>
 *   <li>값이 없으면 0으로 바꾸지 않는다: result null + status "계산 안 함" + reason</li>
 *   <li>입력값마다 어디서 왔는지(재무 API 필드, 시세 기준일)를 남긴다</li>
 *   <li>판단 표현은 넣지 않는다</li>
 * </ul>
 * 반올림은 파이썬 {@code round(x, n)}과 같다 — double의 정확한 십진 값을 half-even으로 자른다({@link #pyRound}).
 * 골든 테스트가 파이썬 결과와 비트 단위로 같은지 확인한다.
 */
public final class Formulas {

    public static final String DONE = "계산됨";
    public static final String SKIP = "계산 안 함";

    private Formulas() {
    }

    // ───────────────────────── 금액 ─────────────────────────

    private static final Pattern FLOAT = Pattern.compile("[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?");

    /** "1,234" · "(1,234)"(음수) · "-" · "" → 원 단위 정수. 해석할 수 없으면 null(0이 아니다). */
    public static Long amount(Object v) {
        if (v == null) return null;
        String s = v.toString().strip().replace(",", "");
        if (s.isEmpty() || s.equals("-")) return null;
        boolean neg = s.startsWith("(") && s.endsWith(")");
        int a = 0, b = s.length();
        while (a < b && (s.charAt(a) == '(' || s.charAt(a) == ')')) a++;
        while (b > a && (s.charAt(b - 1) == '(' || s.charAt(b - 1) == ')')) b--;
        s = s.substring(a, b).strip();
        if (!FLOAT.matcher(s).matches()) return null;
        double d = Double.parseDouble(s);
        if (Double.isNaN(d) || Double.isInfinite(d)) return null;
        long n = (long) d;   // 파이썬 int(float(s)) — 0 쪽으로 자른다
        return neg ? -n : n;
    }

    /** 파이썬 {@code round(x, nd)}. */
    public static double pyRound(double x, int nd) {
        if (Double.isNaN(x) || Double.isInfinite(x)) return x;
        return new BigDecimal(x).setScale(nd, RoundingMode.HALF_EVEN).doubleValue();
    }

    /** 정수는 그대로, 실수는 반올림(파이썬에서 round(int, n)은 int를 돌려준다). */
    public static Number round(Number v, int nd) {
        if (v == null) return null;
        if (v instanceof Double || v instanceof Float) return pyRound(v.doubleValue(), nd);
        return v;
    }

    /** a ÷ b. 둘 중 하나라도 없거나 b가 0이면 null(0으로 바꾸지 않음). */
    public static Double ratio(Number a, Number b) {
        if (a == null || b == null || b.doubleValue() == 0) return null;
        return a.doubleValue() / b.doubleValue();
    }

    // ───────────────────────── Source ─────────────────────────

    /** Source. kind: 재무 API | 원문 표 | 원문 문단 | 시세 | 계산 | 업종 피어 */
    public static Map<String, Object> src(String kind, String label) {
        return src(kind, label, null, null, null, null);
    }

    public static Map<String, Object> src(String kind, String label, String rceptNo, String pid, String field, String url) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("kind", kind);
        out.put("label", label);
        if (rceptNo != null && !rceptNo.isEmpty()) {
            out.put("rceptNo", rceptNo);
            out.put("url", url != null && !url.isEmpty() ? url : Dart.dartUrl(rceptNo));
        } else if (url != null && !url.isEmpty()) {
            out.put("url", url);
        }
        if (pid != null && !pid.isEmpty()) out.put("pid", pid);
        if (field != null && !field.isEmpty()) out.put("field", field);
        return out;
    }

    static final Map<String, String> FIELD_LABEL = Map.of(
            "thstrm_amount", "당기", "frmtrm_amount", "전기", "bfefrmtrm_amount", "전전기",
            "thstrm_add_amount", "당기 누적", "frmtrm_add_amount", "전기 누적", "frmtrm_q_amount", "전기 같은 분기");

    /** 재무 API 한 행·한 필드의 출처. 행이 없으면 null. */
    public static Map<String, Object> finSource(Map<String, Object> row, String field, String label, String fsDiv) {
        if (row == null || row.isEmpty()) return null;
        String nm = Rows.str(row, "account_nm", "");
        String period = FIELD_LABEL.getOrDefault(field, field);
        Object year = row.get("bsns_year");
        String head = Rows.truthy(year) ? year + "년 보고서 · " + nm : nm;
        String lab = label != null && !label.isEmpty() ? label
                : head + " " + period + (fsDiv != null && !fsDiv.isEmpty() ? " (" + fsDiv + ")" : "");
        return src("재무 API", lab, Rows.orNull(Rows.str(row, "rcept_no")), null, field, null);
    }

    // ───────────────────────── Formula ─────────────────────────

    /** FormulaInput. */
    public static Map<String, Object> inp(String name, Object value, String unit, Map<String, Object> source, String note) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("name", name);
        out.put("value", value);
        out.put("unit", unit);
        if (source != null && !source.isEmpty()) out.put("source", source);
        if (note != null && !note.isEmpty()) out.put("note", note);
        return out;
    }

    public static Map<String, Object> inp(String name, Object value, String unit, Map<String, Object> source) {
        return inp(name, value, unit, source, null);
    }

    public static Map<String, Object> inp(String name, Object value, String unit) {
        return inp(name, value, unit, null, null);
    }

    /** Formula. result가 null이면 '계산 안 함'이고 reason이 반드시 붙는다. */
    public static Map<String, Object> formula(String fid, String label, String expr, List<Map<String, Object>> inputs,
                                              Number result, String unit, String reason, List<String> notes, Integer digits) {
        if (result != null && digits != null) {
            result = round(result, digits);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", fid);
        out.put("label", label);
        out.put("expr", expr);
        out.put("inputs", inputs);
        out.put("result", result);
        out.put("unit", unit);
        out.put("status", result != null ? DONE : SKIP);
        out.put("notes", notes == null ? new ArrayList<>() : new ArrayList<>(notes));
        if (result == null) {
            List<String> missing = new ArrayList<>();
            for (Map<String, Object> i : inputs) {
                if (i.get("value") == null) missing.add((String) i.get("name"));
            }
            out.put("reason", reason != null && !reason.isEmpty() ? reason
                    : (!missing.isEmpty() ? "입력값 없음: " + String.join(", ", missing) : "계산 조건을 충족하지 않음"));
        } else if (reason != null && !reason.isEmpty()) {
            out.put("reason", reason);
        }
        return out;
    }

    public static Map<String, Object> formula(String fid, String label, String expr, List<Map<String, Object>> inputs,
                                              Number result, String unit) {
        return formula(fid, label, expr, inputs, result, unit, null, null, null);
    }
}
