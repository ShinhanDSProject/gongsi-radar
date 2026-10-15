package com.gongsiradar.data.source;

import com.gongsiradar.data.client.DataGoKrClient;
import com.gongsiradar.data.client.SourceHttp;
import com.gongsiradar.data.support.Dart;
import com.gongsiradar.data.support.Rows;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * OpenDART(+ 공공데이터포털 시세). 원천 API 키는 Spring에만 있다(AI 서버는 내부 데이터 API로만 받는다).
 * <p>
 * 응답을 디스크에 캐시한다({@code gongsi.data.cache-dir}/opendart). 원문 ZIP은 접수 후 바뀌지 않으므로 접수번호 키로
 * 영구 캐시하고, 재무·목록 응답도 같은 요청을 다시 보내지 않도록 캐시한다(일 20,000건 한도 관리).
 * 오류 코드 013(데이터 없음)도 HTTP 200으로 오므로 본문의 status를 항상 검사한다 — 000만 캐시하고,
 * 013은 캐시하지 않으며(나중에 생길 수 있음), 020(일 한도 초과)과 그 밖의 코드는 예외로 올린다.
 * <p>
 * 파이썬 {@code OpenDartSource}를 그대로 옮겼다. 호출 경로·파라미터는 문서대로 맞췄지만 <b>실키로 검증하지 않았다</b>.
 */
public class OpenDartDataSource implements RadarSource {

    static final String BASE = "https://opendart.fss.or.kr/api";
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {};
    private static final TypeReference<List<Map<String, Object>>> LIST = new TypeReference<>() {};
    private static final TypeReference<List<String>> STRINGS = new TypeReference<>() {};
    private static final DateTimeFormatter YMD = DateTimeFormatter.BASIC_ISO_DATE;

    private final String key;
    private final Path cache;
    private final Path peersFile;
    private final SourceHttp http;
    private final Clock clock;
    private final AtomicLong calls = new AtomicLong();
    private final DataGoKrClient market;
    /** 재시도 사이 대기(테스트에서 0으로) */
    private final Duration retryWait;

    public OpenDartDataSource(String apiKey, String dataGoKrKey, Path cacheRoot, Path peersFile, SourceHttp http,
                              Clock clock, Duration retryWait) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new DataSourceException("OPENDART_API_KEY가 없습니다. 서버 환경변수로 설정하세요(키는 1개만, 제3자 공유 금지).");
        }
        this.key = apiKey;
        this.cache = cacheRoot.resolve("opendart");
        try {
            Files.createDirectories(cache);
        } catch (IOException e) {
            throw new DataSourceException("캐시 디렉터리를 만들지 못했습니다: " + cache, e);
        }
        this.peersFile = peersFile;
        this.http = http;
        this.clock = clock;
        this.retryWait = retryWait;
        this.market = new DataGoKrClient(dataGoKrKey, cacheRoot, http, clock, calls);
    }

    @Override
    public String name() {
        return "opendart";
    }

    @Override
    public long calls() {
        return calls.get();
    }

    private LocalDate today() {
        return LocalDate.now(clock);
    }

    // ───────────────────────── 공통 ─────────────────────────

    /** 실제 호출. 마감 시즌 지연·SSL 오류에 대비해 세 번까지(2초·4초 대기) 시도한다. */
    private byte[] get(String endpoint, Map<String, Object> params) {
        calls.incrementAndGet();
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("crtfc_key", key);
        p.putAll(params);
        IOException last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return http.get(BASE + "/" + endpoint, p, Duration.ofSeconds(60));
            } catch (IOException e) {
                last = e;
                if (attempt < 2) sleep(retryWait.multipliedBy(2L * (attempt + 1)));
            }
        }
        throw new DataSourceException("OpenDART " + endpoint + " 호출 실패: " + last.getMessage(), last);
    }

    private Map<String, Object> getJson(String endpoint, Map<String, Object> params) {
        calls.incrementAndGet();
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("crtfc_key", key);
        p.putAll(params);
        Exception last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return JSON.readValue(http.get(BASE + "/" + endpoint, p, Duration.ofSeconds(60)), MAP);
            } catch (IOException e) {   // JSON이 아닌 응답도 여기로 온다(파이썬 ValueError와 같다)
                last = e;
                if (attempt < 2) sleep(retryWait.multipliedBy(2L * (attempt + 1)));
            }
        }
        throw new DataSourceException("OpenDART " + endpoint + " 호출 실패: " + last.getMessage(), last);
    }

    private static void sleep(Duration d) {
        try {
            Thread.sleep(d.toMillis());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private Map<String, Object> cachedJson(String name, String endpoint, Map<String, Object> params) {
        Path p = cache.resolve(name + ".json");
        if (Files.exists(p)) {
            return read(p, MAP);
        }
        Map<String, Object> d = getJson(endpoint, params);
        String status = Rows.str(d, "status");
        if ("020".equals(status)) {
            throw new DataSourceException("OpenDART 일 호출 한도(오류 020)를 넘었습니다.");
        }
        if (!"000".equals(status) && !"013".equals(status)) {
            throw new DataSourceException("OpenDART 오류 " + status + ": " + d.get("message"));
        }
        if ("000".equals(status)) {     // 데이터 없음(013)은 캐시하지 않는다(나중에 생길 수 있음)
            write(p, d);
        }
        return d;
    }

    private static <T> T read(Path p, TypeReference<T> type) {
        try {
            return JSON.readValue(p.toFile(), type);
        } catch (IOException e) {
            throw new DataSourceException("캐시 파일을 읽지 못했습니다: " + p, e);
        }
    }

    private static void write(Path p, Object value) {
        try {
            Files.createDirectories(p.getParent());
            JSON.writeValue(p.toFile(), value);
        } catch (IOException e) {
            // 캐시 쓰기 실패는 응답을 버리지 않는다
        }
    }

    // ───────────────────────── 회사 목록(corpCode.xml) ─────────────────────────

    private List<Map<String, Object>> corps() {
        Path p = cache.resolve("corp_codes.json");
        if (!Files.exists(p)) {
            byte[] raw = get("corpCode.xml", Map.of());
            write(p, parseCorpCodes(raw));
        }
        return read(p, LIST);
    }

    /** corpCode.xml ZIP의 첫 파일에서 {@code <list>} 항목을 꺼낸다. 고유번호는 문자열로 둔다(앞자리 0). */
    static List<Map<String, Object>> parseCorpCodes(byte[] zip) {
        try (ZipInputStream z = new ZipInputStream(new ByteArrayInputStream(zip))) {
            ZipEntry e = z.getNextEntry();
            if (e == null) {
                throw new DataSourceException("corpCode.xml ZIP이 비어 있습니다.");
            }
            return parseCorpXml(z);
        } catch (IOException | XMLStreamException e) {
            throw new DataSourceException("corpCode.xml을 읽지 못했습니다: " + e.getMessage(), e);
        }
    }

    private static List<Map<String, Object>> parseCorpXml(InputStream in) throws XMLStreamException {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        XMLStreamReader r = f.createXMLStreamReader(in);
        List<Map<String, Object>> out = new ArrayList<>();
        Map<String, String> cur = null;
        while (r.hasNext()) {
            int ev = r.next();
            if (ev == XMLStreamConstants.START_ELEMENT) {
                String tag = r.getLocalName();
                if ("list".equals(tag)) {
                    cur = new LinkedHashMap<>();
                } else if (cur != null) {
                    cur.put(tag, r.getElementText());
                }
            } else if (ev == XMLStreamConstants.END_ELEMENT && "list".equals(r.getLocalName()) && cur != null) {
                out.add(Rows.m("corp_code", strip(cur.get("corp_code")), "corp_name", strip(cur.get("corp_name")),
                        "stock_code", strip(cur.get("stock_code"))));
                cur = null;
            }
        }
        return out;
    }

    private static String strip(String s) {
        return s == null ? "" : s.strip();
    }

    // ───────────────────────── 인터페이스 ─────────────────────────

    @Override
    public Map<String, Object> resolve(String query) {
        List<Map<String, Object>> corps = corps();
        for (Map<String, Object> c : corps) {
            boolean listed = Rows.truthy(c.get("stock_code"));
            if ((query.equals(c.get("corp_code")) || query.equals(c.get("stock_code")))
                    && (listed || query.equals(c.get("corp_code")))) {
                return c;
            }
        }
        for (Map<String, Object> c : corps) {
            if (query.equals(c.get("corp_name")) && Rows.truthy(c.get("stock_code"))) {
                return c;
            }
        }
        throw new DataSourceException("회사를 찾지 못했습니다: " + query);
    }

    @Override
    public Map<String, Object> findReport(String corpCode, int bsnsYear, String reprtCode) {
        Dart.ReprtInfo info = Dart.reprt(reprtCode);
        LocalDate endD = today().isBefore(LocalDate.of(bsnsYear + 1, 12, 31)) ? today() : LocalDate.of(bsnsYear + 1, 12, 31);
        String end = endD.format(YMD);
        Map<String, Object> params = Rows.m("corp_code", corpCode, "bgn_de", bsnsYear + "0101", "end_de", end,
                "last_reprt_at", "Y", "pblntf_ty", "A", "pblntf_detail_ty", info.detail(), "page_count", 100);
        Map<String, Object> d = cachedJson("list_" + corpCode + "_" + bsnsYear + "_" + info.detail() + "_" + end,
                "list.json", params);
        String tag = "(" + bsnsYear + "." + info.mm() + ")";
        String tail = info.name().substring(info.name().length() - 4);
        List<Map<String, Object>> hits = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(d.get("list"))) {
            String nm = Rows.str(r, "report_nm", "");
            if (nm.contains(tag) && nm.contains(tail)) hits.add(r);
        }
        if (hits.isEmpty()) {
            throw new DataSourceException(bsnsYear + "년 " + info.name() + "를 찾지 못했습니다(12월 결산 법인만 지원).");
        }
        hits.sort(Comparator.comparing(x -> Rows.str(x, "rcept_dt", "")));
        Map<String, Object> out = new LinkedHashMap<>(hits.get(hits.size() - 1));   // last_reprt_at=Y: 정정 반영된 최종본
        out.put("bsns_year", bsnsYear);
        out.put("reprt_code", reprtCode);
        out.put("url", Dart.dartUrl(Rows.str(out, "rcept_no")));
        out.put("is_correction", Rows.str(out, "rm", "").contains("정")
                || Rows.str(out, "report_nm", "").contains("[기재정정]"));
        return out;
    }

    @Override
    public byte[] document(String rceptNo) {
        Path p = cache.resolve("documents").resolve(rceptNo + ".zip");
        try {
            if (Files.exists(p)) {
                return Files.readAllBytes(p);
            }
            byte[] data = get("document.xml", Rows.m("rcept_no", rceptNo));
            if (data.length < 2 || data[0] != 'P' || data[1] != 'K') {
                String head = new String(data, 0, Math.min(200, data.length), StandardCharsets.UTF_8);
                throw new DataSourceException("원문 ZIP 대신 오류 응답: " + head);
            }
            Files.createDirectories(p.getParent());
            Files.write(p, data);
            return data;
        } catch (IOException e) {
            throw new DataSourceException("원문 ZIP 캐시 오류: " + e.getMessage(), e);
        }
    }

    @Override
    public Financials financials(String corpCode, int bsnsYear, String reprtCode) {
        for (String fs : List.of("CFS", "OFS")) {   // 연결이 없으면 별도로 폴백
            Map<String, Object> d = cachedJson("fnltt_" + corpCode + "_" + bsnsYear + "_" + reprtCode + "_" + fs,
                    "fnlttSinglAcntAll.json", Rows.m("corp_code", corpCode, "bsns_year", String.valueOf(bsnsYear),
                            "reprt_code", reprtCode, "fs_div", fs));
            if ("000".equals(d.get("status")) && Rows.truthy(d.get("list"))) {
                return new Financials(Rows.list(d.get("list")), fs);
            }
        }
        throw new DataSourceException("재무제표 데이터가 없습니다(013). 2015년 이전 사업연도는 제공되지 않습니다.");
    }

    @Override
    public List<Map<String, Object>> peers(String corpCode, int bsnsYear, String reprtCode) {
        if (peersFile == null || !Files.exists(peersFile)) {
            return new ArrayList<>();
        }
        List<String> codes = new ArrayList<>();
        for (String c : read(peersFile, STRINGS)) {
            if (!c.equals(corpCode)) codes.add(c);
        }
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int k = 0; k < codes.size(); k += 100) {   // 다중회사 주요계정: 한 번에 최대 100개사
            String batch = String.join(",", codes.subList(k, Math.min(k + 100, codes.size())));
            String digest = sha1(batch).substring(0, 10);
            Map<String, Object> d = cachedJson("multi_" + bsnsYear + "_" + reprtCode + "_" + digest, "fnlttMultiAcnt.json",
                    Rows.m("corp_code", batch, "bsns_year", String.valueOf(bsnsYear), "reprt_code", reprtCode));
            for (Map<String, Object> r : Rows.list(d.get("list"))) {
                if ("CFS".equals(Rows.str(r, "fs_div", "CFS"))) rows.add(r);
            }
        }
        return rows;
    }

    private static String sha1(String s) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(s.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    @Override
    public List<Map<String, Object>> lawsuits(String corpCode, String bgn, String end) {
        Map<String, Object> d = cachedJson("lwstLg_" + corpCode + "_" + bgn + "_" + end, "lwstLg.json",
                Rows.m("corp_code", corpCode, "bgn_de", bgn, "end_de", end));
        return Rows.list(d.get("list"));
    }

    /** corpCode.xml에는 업종·시장이 없다(null). 업종은 기업개황을 회사별로 불러야 해서 목록에서는 생략한다. */
    @Override
    public List<Map<String, Object>> companies() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> c : corps()) {
            if (!Rows.truthy(c.get("stock_code"))) continue;
            out.add(Rows.m("corp_code", c.get("corp_code"), "corp_name", c.get("corp_name"),
                    "stock_code", c.get("stock_code"), "induty", null, "induty_code", null, "market", null));
        }
        return out;
    }

    @Override
    public List<Map<String, Object>> filings(String corpCode) {
        LocalDate today = today();
        String end = today.format(YMD);
        Map<String, Object> d = cachedJson("list_" + corpCode + "_A_" + end, "list.json",
                Rows.m("corp_code", corpCode, "bgn_de", (today.getYear() - 3) + "0101", "end_de", end,
                        "last_reprt_at", "Y", "pblntf_ty", "A", "page_count", 100));
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(d.get("list"))) {
            Map<String, Object> row = Dart.filingRow(r, true);   // 원문은 document.xml로 받을 수 있음
            if (row != null) out.add(row);
        }
        out.sort(Comparator.comparing((Map<String, Object> x) -> Rows.str(x, "rcept_dt", "")).reversed());
        return out;
    }

    @Override
    public Map<String, Object> governance(String corpCode, int bsnsYear, String reprtCode) {
        Map<String, Object> params = Rows.m("corp_code", corpCode, "bsns_year", String.valueOf(bsnsYear), "reprt_code", reprtCode);
        List<List<Map<String, Object>>> parts = new ArrayList<>();
        for (String ep : List.of("hyslrSttus", "exctvSttus", "otrCprInvstmntSttus")) {
            parts.add(Dart.rows(cachedJson(ep + "_" + corpCode + "_" + bsnsYear + "_" + reprtCode, ep + ".json", params)));
        }
        Map<String, Object> g = Dart.gov(parts.get(0), parts.get(1), parts.get(2));
        if (!(Rows.truthy(g.get("shareholders")) || Rows.truthy(g.get("executives")) || Rows.truthy(g.get("investments")))) {
            throw new DataSourceException(bsnsYear + "년 지배구조 데이터가 없습니다(013).");
        }
        return g;
    }

    @Override
    public List<Map<String, Object>> market(String stockCode) {
        return market.prices(stockCode);
    }

    /**
     * 전 종목 시세를 날짜별로 받아 종목코드 → 행 목록으로 바꾼다.
     * <p>
     * 종목별로 부르면 2,500번이 넘는다. getStockPriceInfo는 basDt 하나로 전 종목을 돌려주므로 날짜별로 부르고,
     * 지난 날짜는 바뀌지 않으니 영구 캐시한다. 1년을 매일 받으면 첫 계산에 250번이라, 최근 5주는 매일·그 이전은 금요일만 받는다.
     */
    @Override
    public Map<String, List<Map<String, Object>>> marketHistory() {
        Map<String, List<Map<String, Object>>> out = new LinkedHashMap<>();
        if (!market.hasKey()) {
            return out;
        }
        LocalDate today = today();
        for (int back = 0; back < 372; back++) {
            LocalDate d = today.minusDays(back);
            DayOfWeek w = d.getDayOfWeek();
            boolean weekday = w != DayOfWeek.SATURDAY && w != DayOfWeek.SUNDAY;
            if (weekday && (back <= 35 || w == DayOfWeek.FRIDAY)) {
                for (Map<String, Object> it : market.byDate(d.format(YMD))) {
                    out.computeIfAbsent(Rows.str(it, "srtnCd", ""), k -> new ArrayList<>()).add(it);
                }
            }
        }
        return out;
    }

    @Override
    public List<Map<String, Object>> indexSeries(String name) {
        return market.indexSeries(name);
    }

    /** 최근 정기공시(사업·반기·분기). corp_code 없이 부르면 기간이 3개월 이내여야 한다. */
    @Override
    public List<Map<String, Object>> recentFilings() {
        int days = 30;
        LocalDate today = today();
        String bgn = today.minusDays(Math.min(days, 89)).format(YMD);
        String end = today.format(YMD);
        Map<String, Object> d = cachedJson("recent_A_" + bgn + "_" + end, "list.json",
                Rows.m("bgn_de", bgn, "end_de", end, "pblntf_ty", "A", "page_count", 100));
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : Rows.list(d.get("list"))) {
            Map<String, Object> row = Dart.filingRow(r, true);
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

    /** 기업개황(company.json)의 업종 코드(KSIC). 회사마다 한 번 부르고 캐시한다. */
    @Override
    public String indutyCode(String corpCode) {
        Map<String, Object> d;
        try {
            d = cachedJson("company_" + corpCode, "company.json", Rows.m("corp_code", corpCode));
        } catch (DataSourceException e) {
            return null;
        }
        return "000".equals(d.get("status")) ? Rows.orNull(Rows.str(d, "induty_code")) : null;
    }
}
