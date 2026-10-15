package com.gongsiradar.data;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 가상 기업 샘플(저장소 루트 {@code samples/data/}). AI 서버의 단독 실행·테스트와 같은 파일을 읽는다.
 * <p>
 * 파일 이름과 모양은 OpenDART·공공데이터포털 응답 그대로다({@code samples/build_samples.py}가 만든다).
 * {@link #calls()}는 파이썬 SampleSource와 같은 규칙으로 센다 — 응답 파일을 읽을 때마다 1(없는 파일도 1),
 * 원문 ZIP 1, 시세는 파일이 있을 때만 1. 회사 목록(corp_codes.json)은 세지 않는다.
 * 수집 작업의 호출 예산 테스트가 이 수에 기대므로 바꾸지 않는다.
 */
public class SampleDataSource implements RadarSource {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {};
    private static final TypeReference<List<Map<String, Object>>> LIST = new TypeReference<>() {};

    private final Path dir;
    private final AtomicLong calls = new AtomicLong();

    public SampleDataSource(Path dataDir) {
        this.dir = dataDir;
        if (!Files.exists(dir.resolve("list.json"))) {
            throw new DataSourceException("샘플 데이터가 없습니다: " + dir.toAbsolutePath()
                    + " (저장소 루트에서 python samples/build_samples.py 실행)");
        }
    }

    public Path dir() {
        return dir;
    }

    @Override
    public String name() {
        return "sample";
    }

    @Override
    public long calls() {
        return calls.get();
    }

    // ───────────────────────── 파일 읽기 ─────────────────────────

    private Map<String, Object> json(String name) {
        calls.incrementAndGet();
        Path p = dir.resolve(name);
        if (!Files.exists(p)) {
            return Rows.m("status", "013", "message", "조회된 데이타가 없습니다.", "list", new ArrayList<>());
        }
        return read(p, MAP);
    }

    private static <T> T read(Path p, TypeReference<T> type) {
        try {
            return JSON.readValue(p.toFile(), type);
        } catch (IOException e) {
            throw new UncheckedIOException("샘플 파일을 읽지 못했습니다: " + p, e);
        }
    }

    private List<Map<String, Object>> corps() {
        return read(dir.resolve("corp_codes.json"), LIST);
    }

    private boolean hasZip(Object rceptNo) {
        return Files.exists(dir.resolve("filings").resolve(rceptNo + ".zip"));
    }

    // ───────────────────────── 인터페이스 ─────────────────────────

    @Override
    public Map<String, Object> resolve(String query) {
        List<Map<String, Object>> corps = corps();
        for (Map<String, Object> c : corps) {
            if (query != null && (query.equals(c.get("corp_code")) || query.equals(c.get("stock_code"))
                    || query.equals(c.get("corp_name")))) {
                return c;
            }
        }
        throw new DataSourceException("샘플에 없는 회사입니다: " + query + " (가능: "
                + corps.stream().map(c -> "'" + c.get("stock_code") + "'").toList() + ")");
    }

    @Override
    public Map<String, Object> findReport(String corpCode, int bsnsYear, String reprtCode) {
        Dart.ReprtInfo info = Dart.reprt(reprtCode);
        String tag = "(" + bsnsYear + "." + info.mm() + ")";
        for (Map<String, Object> r : Rows.list(json("list.json").get("list"))) {
            String nm = Rows.str(r, "report_nm", "");
            if (corpCode.equals(r.get("corp_code")) && nm.contains(tag) && nm.contains(info.name())) {
                Map<String, Object> out = new LinkedHashMap<>(r);
                out.put("bsns_year", bsnsYear);
                out.put("reprt_code", reprtCode);
                out.put("url", Dart.dartUrl(Rows.str(r, "rcept_no")));
                return out;
            }
        }
        throw new DataSourceException(bsnsYear + "년 " + info.name() + "를 찾지 못했습니다.");
    }

    @Override
    public byte[] document(String rceptNo) {
        calls.incrementAndGet();
        Path p = dir.resolve("filings").resolve(rceptNo + ".zip");
        if (!Files.exists(p)) {
            throw new DataSourceException("원문 ZIP 없음: " + p);
        }
        try {
            return Files.readAllBytes(p);
        } catch (IOException e) {
            throw new DataSourceException("원문 ZIP을 읽지 못했습니다: " + p, e);
        }
    }

    @Override
    public Financials financials(String corpCode, int bsnsYear, String reprtCode) {
        for (String fs : List.of("CFS", "OFS")) {
            Map<String, Object> d = json("fnltt_" + corpCode + "_" + bsnsYear + "_" + reprtCode + "_" + fs + ".json");
            if ("000".equals(d.get("status")) && Rows.truthy(d.get("list"))) {
                return new Financials(Rows.list(d.get("list")), fs);
            }
        }
        // 피어: 단일회사 전체 재무 파일이 없으면 다중회사 주요계정(피어 파일)의 그 회사 행으로 대신한다
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(json("peers_" + bsnsYear + "_" + reprtCode + ".json").get("list"))) {
            if (corpCode.equals(r.get("corp_code"))) {
                rows.add(r);
            }
        }
        if (!rows.isEmpty()) {
            return new Financials(rows, Rows.str(rows.get(0), "fs_div", "CFS"));
        }
        throw new DataSourceException("재무제표 데이터가 없습니다(013).");
    }

    @Override
    public List<Map<String, Object>> peers(String corpCode, int bsnsYear, String reprtCode) {
        return Rows.list(json("peers_" + bsnsYear + "_" + reprtCode + ".json").get("list"));
    }

    @Override
    public List<Map<String, Object>> lawsuits(String corpCode, String bgn, String end) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(json("lwstLg_" + corpCode + ".json").get("list"))) {
            String d = Rows.str(r, "lgd", "").replace("-", "");
            if (bgn.compareTo(d) <= 0 && d.compareTo(end) <= 0) {
                out.add(r);
            }
        }
        return out;
    }

    @Override
    public List<Map<String, Object>> companies() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> c : corps()) {
            if (!Rows.truthy(c.get("stock_code"))) continue;
            out.add(Rows.m("corp_code", c.get("corp_code"), "corp_name", c.get("corp_name"),
                    "stock_code", Rows.str(c, "stock_code", ""), "induty", c.get("induty"),
                    "induty_code", c.get("induty_code"), "market", c.get("market")));
        }
        return out;
    }

    @Override
    public List<Map<String, Object>> filings(String corpCode) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(json("list.json").get("list"))) {
            if (!corpCode.equals(r.get("corp_code"))) continue;
            Map<String, Object> row = Dart.filingRow(r, hasZip(r.get("rcept_no")));
            if (row != null) out.add(row);
        }
        out.sort(Comparator.comparing((Map<String, Object> x) -> Rows.str(x, "rcept_dt", "")).reversed());
        return out;
    }

    @Override
    public Map<String, Object> governance(String corpCode, int bsnsYear, String reprtCode) {
        String tail = corpCode + "_" + bsnsYear + "_" + reprtCode + ".json";
        Map<String, Object> g = Dart.gov(Dart.rows(json("hyslrSttus_" + tail)), Dart.rows(json("exctvSttus_" + tail)),
                Dart.rows(json("otrCprInvstmntSttus_" + tail)));
        if (!(Rows.truthy(g.get("shareholders")) || Rows.truthy(g.get("executives")) || Rows.truthy(g.get("investments")))) {
            throw new DataSourceException(bsnsYear + "년 지배구조 데이터가 없습니다(013).");
        }
        return g;
    }

    @Override
    public List<Map<String, Object>> market(String stockCode) {
        Path p = dir.resolve("market_" + stockCode + ".json");
        if (!Files.exists(p)) {
            return new ArrayList<>();
        }
        calls.incrementAndGet();
        return Dart.items(read(p, MAP));
    }

    // ───────────────────────── 시장 화면 ─────────────────────────

    /** 종목코드 → 일별 시세. 샘플은 회사별 파일을 모두 읽는다. */
    @Override
    public Map<String, List<Map<String, Object>>> marketHistory() {
        Map<String, List<Map<String, Object>>> out = new LinkedHashMap<>();
        for (Map<String, Object> c : companies()) {
            List<Map<String, Object>> rows = market(Rows.str(c, "stock_code"));
            if (!rows.isEmpty()) {
                out.put(Rows.str(c, "stock_code"), rows);
            }
        }
        return out;
    }

    /** 공식 지수는 샘플에 없다 → 시장 화면이 대체 지수를 만든다. */
    @Override
    public List<Map<String, Object>> indexSeries(String name) {
        return new ArrayList<>();
    }

    @Override
    public List<Map<String, Object>> recentFilings() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(json("list.json").get("list"))) {
            Map<String, Object> row = Dart.filingRow(r, hasZip(r.get("rcept_no")));
            if (row != null) {
                Map<String, Object> merged = new LinkedHashMap<>(r);
                merged.putAll(row);
                out.add(merged);
            }
        }
        out.sort(Comparator.comparing((Map<String, Object> x) -> Rows.str(x, "rcept_dt", ""))
                .thenComparing(x -> Rows.str(x, "rcept_no", "")).reversed());
        return out;
    }

    @Override
    public String indutyCode(String corpCode) {
        for (Map<String, Object> c : companies()) {
            if (corpCode.equals(c.get("corp_code"))) {
                return Rows.str(c, "induty_code");
            }
        }
        return null;
    }
}
