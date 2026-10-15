package com.gongsiradar.data.support;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 원천 응답 행(Map) 다루기 도우미.
 * <p>
 * 원천(OpenDART·공공데이터포털) 응답은 필드가 많고 모양이 자주 바뀐다. 레코드로 고정하지 않고
 * 받은 모양 그대로(Map) 들고 다닌다 — 내부 데이터 API가 원천 필드를 그대로 AI 서버에 넘겨야 하기 때문이다.
 * 파이썬 radar 코드의 {@code dict.get}·참거짓 판정과 같은 의미를 내도록 맞췄다.
 */
public final class Rows {

    private Rows() {
    }

    /** 순서를 지키고 null 값을 허용하는 Map. {@code m("a", 1, "b", null)} */
    public static Map<String, Object> m(Object... kv) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kv.length; i += 2) {
            out.put((String) kv[i], kv[i + 1]);
        }
        return out;
    }

    /** 값을 문자열로. 없으면 null. */
    public static String str(Map<String, ?> row, String key) {
        if (row == null) return null;
        Object v = row.get(key);
        return v == null ? null : v.toString();
    }

    /** 값을 문자열로. 없거나 null이면 기본값(파이썬 {@code r.get(k) or d}에 가깝다). */
    public static String str(Map<String, ?> row, String key, String dflt) {
        String s = str(row, key);
        return s == null ? dflt : s;
    }

    /** 파이썬 참거짓: null·빈 문자열·0·false·빈 컬렉션은 거짓. */
    public static boolean truthy(Object v) {
        if (v == null) return false;
        if (v instanceof Boolean b) return b;
        if (v instanceof String s) return !s.isEmpty();
        if (v instanceof Number n) return n.doubleValue() != 0;
        if (v instanceof Collection<?> c) return !c.isEmpty();
        if (v instanceof Map<?, ?> mm) return !mm.isEmpty();
        return true;
    }

    /** 비어 있지 않은 문자열이면 그대로, 아니면 null(파이썬 {@code x or None}). */
    public static String orNull(String s) {
        return s == null || s.isEmpty() ? null : s;
    }

    @SuppressWarnings("unchecked")
    public static List<Map<String, Object>> list(Object v) {
        return v instanceof List<?> l ? (List<Map<String, Object>>) l : List.of();
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> map(Object v) {
        return v instanceof Map<?, ?> mm ? (Map<String, Object>) mm : Map.of();
    }

    /** DB 값(Boolean 또는 TINYINT)을 boolean으로. */
    public static boolean bool(Object v) {
        if (v instanceof Boolean b) return b;
        if (v instanceof Number n) return n.intValue() != 0;
        return false;
    }

    /** 문자열의 공백을 모두 지운다(파이썬 {@code "".join(s.split())}). */
    public static String noSpace(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isWhitespace(c) || Character.isSpaceChar(c) || (c >= 0x1c && c <= 0x1f) || c == 0x85) {
                continue;
            }
            sb.append(c);
        }
        return sb.toString();
    }
}
