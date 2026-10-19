package com.gongsiradar.data.client;

import com.gongsiradar.data.source.DataSourceException;
import com.gongsiradar.data.support.Dart;
import com.gongsiradar.data.support.Rows;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 공공데이터포털 금융위원회 시세(파이썬 {@code DataGoKrMarket}·{@code DataGoKrIndex}).
 * <ul>
 *   <li>주식시세정보 getStockPriceInfo_V2 — 영업일 다음 날 오후에 전일 시세가 올라온다</li>
 *   <li>지수시세정보 getStockMarketIndex_V2 — idxNm=코스피·코스닥, 최대 5년치</li>
 * </ul>
 * 키가 없으면 빈 목록(시장 지표는 '계산 안 함'). 캐시 규칙은 파이썬과 같다 — 종목·지수는 그날 하루, 날짜별 전 종목은
 * 지난 날짜만 영구. 2026-10-19 실키로 V2 주소 검증(시세·지수 필드명은 옛 버전과 같다).
 * <p>
 * [파이썬과 다른 점] 실제 HTTP 호출 수를 호출 카운터에 더한다(캐시 적중은 세지 않는다). 파이썬 OpenDartSource는
 * 시세 호출을 세지 않았지만 샘플 소스는 시세 파일 읽기를 셌다 — 수집 예산이 두 모드에서 같은 뜻이 되게 맞췄다.
 */
public class DataGoKrClient {

    // 2025년 이후 활용신청은 V2 서비스 권한만 준다(옛 주소는 HTTP 403). 바뀌면 환경변수로 덮어쓴다
    static final String PRICE_URL = env("DATA_GO_KR_PRICE_URL",
            "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2");
    static final String INDEX_URL = env("DATA_GO_KR_INDEX_URL",
            "https://apis.data.go.kr/1160100/GetMarketIndexInfoService_V2/getStockMarketIndex_V2");
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {};
    private static final TypeReference<List<Map<String, Object>>> LIST = new TypeReference<>() {};
    private static final DateTimeFormatter YMD = DateTimeFormatter.BASIC_ISO_DATE;

    private final String key;
    private final Path cache;
    private final SourceHttp http;
    private final Clock clock;
    private final AtomicLong calls;

    public DataGoKrClient(String apiKey, Path cacheRoot, SourceHttp http, Clock clock, AtomicLong calls) {
        this.key = apiKey == null || apiKey.isBlank() ? null : apiKey;
        this.cache = cacheRoot.resolve("datagokr");
        this.http = http;
        this.clock = clock;
        this.calls = calls;
    }

    private static String env(String name, String fallback) {
        String v = System.getenv(name);
        return v == null || v.isBlank() ? fallback : v;
    }

    public boolean hasKey() {
        return key != null;
    }

    private LocalDate today() {
        return LocalDate.now(clock);
    }

    private Map<String, Object> fetch(String url, Map<String, Object> params, Duration timeout, String what) {
        calls.incrementAndGet();
        try {
            return JSON.readValue(http.get(url, params, timeout), MAP);
        } catch (IOException e) {   // 연결 실패·HTTP 오류·JSON 아님(키 오류는 XML로 온다)
            throw new DataSourceException("공공데이터포털 " + what + " 호출 실패: " + e.getMessage(), e);
        }
    }

    private static String resultCode(Map<String, Object> d) {
        return Rows.str(Rows.map(Rows.map(d.get("response")).get("header")), "resultCode");
    }

    private static void write(Path p, Object value) {
        try {
            Files.createDirectories(p.getParent());
            JSON.writeValue(p.toFile(), value);
        } catch (IOException e) {
            // 캐시 쓰기 실패는 응답을 버리지 않는다(다음에 다시 부를 뿐)
        }
    }

    private static <T> T read(Path p, TypeReference<T> type) {
        try {
            return JSON.readValue(p.toFile(), type);
        } catch (IOException e) {
            throw new DataSourceException("캐시 파일을 읽지 못했습니다: " + p, e);
        }
    }

    /** 한 종목의 최근 시세(최신일 먼저). likeSrtnCd는 부분 일치라 정확히 같은 종목만 남긴다. */
    public List<Map<String, Object>> prices(String stockCode) {
        int days = 120;
        if (key == null || stockCode == null || stockCode.isEmpty()) {
            return new ArrayList<>();
        }
        LocalDate today = today();
        Path p = cache.resolve("price_" + stockCode + "_" + today.format(YMD) + ".json");
        if (Files.exists(p)) {
            return only(read(p, MAP), stockCode);
        }
        String begin = today.minusDays((int) (days * 1.5)).format(YMD);
        Map<String, Object> d = fetch(PRICE_URL, Rows.m("serviceKey", key, "resultType", "json", "numOfRows", days,
                "pageNo", 1, "likeSrtnCd", stockCode, "beginBasDt", begin), Duration.ofSeconds(30), "시세");
        String code = resultCode(d);
        if (!"00".equals(code)) {
            throw new DataSourceException("공공데이터포털 시세 오류 " + code);
        }
        write(p, d);
        return only(d, stockCode);
    }

    /** 그 날짜의 전 종목 시세. 휴장일이면 빈 목록. 지난 날짜는 바뀌지 않아 영구 캐시한다. */
    public List<Map<String, Object>> byDate(String basDt) {
        Path p = cache.resolve("all_" + basDt + ".json");
        if (Files.exists(p)) {
            return Dart.items(read(p, MAP));
        }
        Map<String, Object> d = fetch(PRICE_URL, Rows.m("serviceKey", key, "resultType", "json", "numOfRows", 5000,
                "pageNo", 1, "basDt", basDt), Duration.ofSeconds(60), "시세");
        if (!"00".equals(resultCode(d))) {
            throw new DataSourceException("공공데이터포털 시세 오류");
        }
        if (basDt.compareTo(today().format(YMD)) < 0) {
            write(p, d);
        }
        return Dart.items(d);
    }

    /** 지수 일별 종가(코스피·코스닥). 그날 하루 캐시. */
    public List<Map<String, Object>> indexSeries(String name) {
        int years = 5;
        if (key == null) {
            return new ArrayList<>();
        }
        LocalDate today = today();
        Path p = cache.resolve("index_" + name + "_" + today.format(YMD) + ".json");
        if (Files.exists(p)) {
            return read(p, LIST);
        }
        String begin = LocalDate.of(today.getYear() - years, today.getMonthValue(), Math.min(today.getDayOfMonth(), 28))
                .format(YMD);
        Map<String, Object> d = fetch(INDEX_URL, Rows.m("serviceKey", key, "resultType", "json", "numOfRows", 2000,
                "pageNo", 1, "idxNm", name, "beginBasDt", begin), Duration.ofSeconds(60), "지수");
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> i : Dart.items(d)) {
            if (name.equals(i.get("idxNm"))) rows.add(i);
        }
        write(p, rows);
        return rows;
    }

    static List<Map<String, Object>> only(Map<String, Object> d, String stockCode) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> i : Dart.items(d)) {
            if (stockCode.equals(i.get("srtnCd"))) out.add(i);
        }
        out.sort(Comparator.comparing((Map<String, Object> i) -> Rows.str(i, "basDt", "")).reversed());
        return out;
    }
}
