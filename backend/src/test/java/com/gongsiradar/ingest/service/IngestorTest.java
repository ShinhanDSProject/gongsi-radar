package com.gongsiradar.ingest.service;

import com.gongsiradar.ingest.repository.IngestStore;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.company.service.CompanyService;
import com.gongsiradar.data.config.DataSourceConfig;
import com.gongsiradar.data.source.IngestedDataSource;
import com.gongsiradar.data.source.RadarSource;
import com.gongsiradar.data.source.SampleDataSource;
import com.gongsiradar.data.source.SourceUnavailableException;
import com.gongsiradar.market.service.MarketOverviewService;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

import javax.sql.DataSource;
import java.sql.Connection;
import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * 일일 수집 테스트(분리 전 파이썬 수집 테스트와 같은 시나리오). 샘플 원천 + H2 인메모리 DB(MariaDB 호환 모드).
 * <p>
 * 왜 H2인가: 테스트마다 빈 DB가 필요하고(멱등·이어 하기·Kill Switch를 처음 상태에서 확인), 실제 MariaDB의 적재 테이블은
 * 개발 중인 앱이 읽고 있어 지울 수 없다(수집 계정에 DELETE가 없다 — 그게 맞다). upsert는 MariaDB 문법
 * {@code INSERT ... ON DUPLICATE KEY UPDATE col = VALUES(col)} 그대로 H2 MariaDB 모드에서 돈다.
 * MariaDB 자체에 대한 확인은 1회 실행 모드 스모크 테스트로 한다.
 */
class IngestorTest {

    static final LocalDate TODAY = LocalDate.of(2026, 10, 15);
    static final Clock CLOCK = Clock.fixed(TODAY.atTime(12, 0).atZone(ZoneId.of("Asia/Seoul")).toInstant(), ZoneId.of("Asia/Seoul"));

    static DataSource db() {
        DriverManagerDataSource ds = new DriverManagerDataSource(
                "jdbc:h2:mem:ingest-" + UUID.randomUUID() + ";MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");
        try (Connection c = ds.getConnection()) {
            ScriptUtils.executeSqlScript(c, new ClassPathResource("ingest/h2-schema.sql"));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        return ds;
    }

    static SampleDataSource sample() {
        return new SampleDataSource(DataSourceConfig.resolveSampleDir("../samples/data"));
    }

    static Ingestor ingestor(RadarSource src, IngestStore store, int budget, LocalDate today) {
        return new Ingestor(src, store, budget, today, LocalDateTime::now, null);
    }

    static Map<String, Integer> counts(IngestStore store) {
        Map<String, Integer> m = new HashMap<>();
        for (String t : List.of(IngestStore.COMPANY, IngestStore.FILING, IngestStore.FINANCIAL_LINE, IngestStore.MARKET_DAILY)) {
            m.put(t, store.count(t));
        }
        return m;
    }

    static Map<String, String> statuses(Ingestor.RunReport rep) {
        return rep.steps().stream().collect(Collectors.toMap(s -> s.step, s -> s.status));
    }

    @Nested
    @TestInstance(TestInstance.Lifecycle.PER_CLASS)
    class 일일_수집 {
        DataSource ds;
        IngestStore store;
        Ingestor.RunReport first;
        Ingestor.RunReport second;
        Map<String, Integer> afterFirst;

        @BeforeAll
        void run() {
            ds = db();
            store = new IngestStore(ds);
            first = ingestor(sample(), store, 15_000, TODAY).run("daily");
            afterFirst = counts(store);
            second = ingestor(sample(), store, 15_000, TODAY).run("daily");
        }

        @Test
        void 모든_단계가_끝나고_적재된다() {
            assertThat(first.steps()).allMatch(s -> "DONE".equals(s.status), first.summary());
            assertThat(afterFirst.get(IngestStore.COMPANY)).isEqualTo(46);
            assertThat(afterFirst.get(IngestStore.FILING)).isEqualTo(23);
            assertThat(afterFirst.get(IngestStore.MARKET_DAILY)).isEqualTo(46 * 262);
            assertThat(afterFirst.get(IngestStore.FINANCIAL_LINE)).isGreaterThan(0);
        }

        @Test
        void 두_번_돌려도_결과가_같다() {
            assertThat(counts(store)).isEqualTo(afterFirst);
            Ingestor.StepResult market = second.steps().stream().filter(s -> s.step.equals("market")).findFirst().orElseThrow();
            assertThat(market.rows).isZero();   // 저장된 마지막 날짜 이후만 쓴다
        }

        @Test
        void 실행_기록이_단계별로_남는다() {
            List<Map<String, Object>> runs = store.recentRuns(100);
            assertThat(runs.stream().filter(r -> first.runUid().equals(r.get("run_uid"))).map(r -> r.get("step")))
                    .containsExactlyInAnyOrder("companies", "filings", "market", "index", "financials", "induty", "documents");
            assertThat(runs).allMatch(r -> r.get("finished_at") != null);
        }

        @Test
        void 회사의_시장과_업종이_적재된다() {
            Map<String, Object> r = new JdbcTemplate(ds).queryForMap(
                    "SELECT market, induty_code, first_seen FROM ingest_company WHERE corp_code = '00999001'");
            assertThat(r.get("market")).isEqualTo("KOSDAQ");
            assertThat(r.get("induty_code")).isEqualTo("20129");
            assertThat(r.get("first_seen").toString()).isEqualTo("2026-10-15");
        }
    }

    /** 적재 DB를 읽어도 원천을 직접 읽은 것과 같은 결과가 나와야 한다(화면이 수집 전후로 달라지지 않는다). */
    @Nested
    @TestInstance(TestInstance.Lifecycle.PER_CLASS)
    class 적재_DB_읽기 {
        DataSource ds;

        @BeforeAll
        void load() {
            ds = db();
            ingestor(sample(), new IngestStore(ds), 15_000, TODAY).run("daily");
        }

        @Test
        void 시장_화면이_같다() {
            Map<String, Object> a = MarketOverviewService.overview(sample(), "ALL");
            IngestedDataSource db = new IngestedDataSource(sample(), ds, CLOCK);
            Map<String, Object> b = MarketOverviewService.overview(db, "ALL");
            for (String k : List.of("capitalization", "sectors", "markets", "indices", "asOf")) {
                assertThat(b.get(k)).as(k).isEqualTo(a.get(k));
            }
            assertThat(ids(b)).isEqualTo(ids(a));
            assertThat(b.get("ingested")).isEqualTo(true);
            assertThat(b.get("newListings")).isEqualTo(List.of());   // 첫 적재분은 신규가 아니다
        }

        @SuppressWarnings("unchecked")
        private List<Object> ids(Map<String, Object> o) {
            return ((List<Map<String, Object>>) o.get("recentFilings")).stream().map(r -> r.get("rceptNo")).toList();
        }

        @Test
        void 기업_목록이_같다() {
            AiClient ai = mock(AiClient.class);
            List<Map<String, Object>> a = new CompanyService(sample(), ai, CLOCK).search("", 50, null, TODAY);
            List<Map<String, Object>> b = new CompanyService(new IngestedDataSource(sample(), ds, CLOCK), ai, CLOCK)
                    .search("", 50, null, TODAY);
            assertThat(b).isEqualTo(a);
        }

        @Test
        void 재무는_원천을_부르지_않고_DB에서_읽는다() {
            SampleDataSource src = sample();
            IngestedDataSource db = new IngestedDataSource(src, ds, CLOCK);
            RadarSource.Financials f = db.financials("00999001", 2025, "11011");
            assertThat(f.fsDiv()).isEqualTo("CFS");
            assertThat(src.calls()).isZero();
            RadarSource.Financials want = sample().financials("00999001", 2025, "11011");
            assertThat(f.rows().stream().collect(Collectors.toMap(r -> r.get("account_nm"), r -> r.get("thstrm_amount"), (x, y) -> x)))
                    .isEqualTo(want.rows().stream().collect(Collectors.toMap(r -> r.get("account_nm"), r -> r.get("thstrm_amount"), (x, y) -> x)));
        }

        @Test
        void 빈_DB면_원천을_쓴다() {
            IngestedDataSource empty = new IngestedDataSource(sample(), db(), CLOCK);
            assertThat(empty.companies()).hasSize(46);
            assertThat(empty.marketHistory()).hasSize(46);
            assertThat(empty.ingested()).isFalse();
        }
    }

    @Test
    void 예산이_떨어지면_PARTIAL로_남기고_다음_실행이_이어_한다() {
        DataSource ds = db();
        IngestStore store = new IngestStore(ds);
        Ingestor.RunReport first = ingestor(sample(), store, 60, TODAY).run("daily");
        assertThat(statuses(first).get("financials")).isEqualTo("PARTIAL");   // 시세가 예산을 다 썼다
        Integer left = new JdbcTemplate(ds).queryForObject(
                "SELECT COUNT(*) FROM ingest_filing WHERE financial_done = FALSE", Integer.class);
        assertThat(left).isGreaterThan(0);
        Ingestor.RunReport second = ingestor(sample(), store, 10_000, TODAY).run("daily");
        assertThat(statuses(second).get("financials")).isEqualTo("DONE");
        assertThat(store.count(IngestStore.FINANCIAL_LINE)).isGreaterThan(0);
    }

    @Test
    void 호출_수는_실제_원천_호출만_센다() {
        IngestStore store = new IngestStore(db());
        SampleDataSource src = sample();
        Ingestor.RunReport rep = ingestor(src, store, 15_000, TODAY).run("daily");
        assertThat((long) rep.calls()).isEqualTo(src.calls());
        Ingestor.StepResult market = rep.steps().stream().filter(s -> s.step.equals("market")).findFirst().orElseThrow();
        assertThat(market.calls).isEqualTo(46);   // 종목 파일 46개
    }

    @Test
    void Kill_Switch가_켜져_있으면_아무것도_하지_않는다() {
        DataSource ds = db();
        new JdbcTemplate(ds).update("INSERT INTO kill_switch_status (active, reason, toggled_by) VALUES (TRUE, '훈련', 'test')");
        IngestStore store = new IngestStore(ds);
        Ingestor.RunReport rep = ingestor(sample(), store, 15_000, TODAY).run("daily");
        assertThat(rep.steps()).extracting(s -> s.status).containsExactly("SKIPPED");
        assertThat(store.count(IngestStore.COMPANY)).isZero();
        assertThat(store.recentRuns(1).get(0).get("status")).isEqualTo("SKIPPED");
    }

    @Test
    void 첫_적재_뒤에_처음_본_회사만_신규다() {
        DataSource ds = db();
        IngestStore store = new IngestStore(ds);
        ingestor(sample(), store, 10_000, TODAY.minusDays(10)).run("daily", List.of("companies"), 3, true);
        assertThat(new IngestedDataSource(sample(), ds, CLOCK).newListings(30)).isEmpty();
        store.upsertCompanies(List.of(Map.of("corp_code", "00555001", "corp_name", "새상장(가상)", "stock_code", "555001",
                "market", "KOSDAQ")), TODAY);
        assertThat(new IngestedDataSource(sample(), ds, CLOCK).newListings(30))
                .extracting(r -> r.get("corp_name")).containsExactly("새상장(가상)");
    }
    @Test
    void 원천_연결이_끊기면_단계를_멈추고_업종을_확인함으로_남기지_않는다() {
        DataSource ds = db();
        IngestStore store = new IngestStore(ds);
        int[] n = {0};
        SampleDataSource flaky = new SampleDataSource(DataSourceConfig.resolveSampleDir("../samples/data")) {
            @Override
            public List<Map<String, Object>> companies() {   // 실데이터처럼 목록에는 업종이 없다 → 업종 단계가 회사마다 부른다
                List<Map<String, Object>> out = new ArrayList<>();
                for (Map<String, Object> c : super.companies()) {
                    Map<String, Object> m = new HashMap<>(c);
                    m.remove("induty_code");
                    out.add(m);
                }
                return out;
            }

            @Override
            public String indutyCode(String corpCode) {
                if (++n[0] > 5) throw new SourceUnavailableException("OpenDART company.json 호출 실패: 연결이 계속 끊김");
                return super.indutyCode(corpCode);
            }
        };
        Ingestor.RunReport rep = ingestor(flaky, store, 15_000, TODAY).run("daily");
        Map<String, String> st = statuses(rep);
        assertThat(st.get("induty")).isEqualTo("PARTIAL");
        assertThat(rep.steps().stream().filter(x -> x.step.equals("induty")).findFirst().orElseThrow().rows).isEqualTo(5);
        assertThat(st).doesNotContainKey("documents");   // 같은 원천을 부르는 다음 단계는 돌리지 않는다
        Integer checked = new JdbcTemplate(ds).queryForObject(
                "SELECT COUNT(*) FROM ingest_company WHERE induty_checked IS NOT NULL", Integer.class);
        assertThat(checked).isEqualTo(5);   // 실패한 회사는 다음 실행이 다시 본다
        assertThat(store.recentRuns(1).get(0).get("status")).isEqualTo("PARTIAL");
    }
}
