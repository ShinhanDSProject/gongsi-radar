package com.gongsiradar.finance;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.TreeSet;

/**
 * JSON 트리 비교(골든 테스트용). 숫자는 값으로 비교한다 — 파이썬은 4.0, Java는 4.0 또는 4로 쓸 수 있어
 * 노드 타입(DoubleNode·LongNode)이 아니라 십진 값이 같은지 본다. 허용 오차는 두지 않는다(정확히 같아야 한다).
 * 배열은 순서까지, 객체는 키 집합까지 같아야 한다. 다른 곳을 경로와 함께 모두 돌려준다.
 */
public final class JsonDiff {

    private JsonDiff() {
    }

    public static List<String> diff(JsonNode want, JsonNode got) {
        List<String> out = new ArrayList<>();
        walk("$", want, got, out);
        return out;
    }

    private static void walk(String path, JsonNode a, JsonNode b, List<String> out) {
        if (out.size() > 50) return;
        if (a.isNumber() && b.isNumber()) {
            if (a.decimalValue().compareTo(b.decimalValue()) != 0) out.add(path + ": " + a + " != " + b);
            return;
        }
        if (a.getNodeType() != b.getNodeType()) {
            out.add(path + ": 타입 " + a.getNodeType() + "(" + clip(a) + ") != " + b.getNodeType() + "(" + clip(b) + ")");
            return;
        }
        if (a.isObject()) {
            TreeSet<String> keys = new TreeSet<>();
            a.fieldNames().forEachRemaining(keys::add);
            TreeSet<String> bk = new TreeSet<>();
            b.fieldNames().forEachRemaining(bk::add);
            if (!keys.equals(bk)) out.add(path + ": 키 " + keys + " != " + bk);
            for (Iterator<String> it = a.fieldNames(); it.hasNext(); ) {
                String k = it.next();
                if (b.has(k)) walk(path + "." + k, a.get(k), b.get(k), out);
            }
        } else if (a.isArray()) {
            if (a.size() != b.size()) out.add(path + ": 길이 " + a.size() + " != " + b.size());
            for (int i = 0; i < Math.min(a.size(), b.size()); i++) walk(path + "[" + i + "]", a.get(i), b.get(i), out);
        } else if (!a.equals(b)) {
            out.add(path + ": " + clip(a) + " != " + clip(b));
        }
    }

    private static String clip(JsonNode n) {
        String s = n.toString();
        return s.length() > 120 ? s.substring(0, 120) + "…" : s;
    }
}
