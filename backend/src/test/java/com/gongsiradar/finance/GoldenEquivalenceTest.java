package com.gongsiradar.finance;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.company.service.CompanyService;
import com.gongsiradar.data.config.DataSourceConfig;
import com.gongsiradar.data.source.SampleDataSource;
import com.gongsiradar.market.service.MarketOverviewService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.InputStream;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 분리 전 파이썬 결과(골든)와 Java 계산이 같은지 — CONTRACT §11.1 "Java 결과는 golden과 같아야 한다".
 * <p>
 * 골든은 {@code backend/src/test/resources/golden/*.json}: 파이썬 SampleSource로 2026-10-15 기준에 뽑은 값이다.
 * 숫자는 허용 오차 없이 값이 같아야 한다(반올림을 파이썬 round와 같게 구현했다). 상세의 business·governance와
 * 그 안내 notes는 AI 서버(/ai/insights)가 만드는 부분이라 AiClient를 목으로 바꿔 골든 값을 돌려주게 하고,
 * 나머지(회사·공시·재무 표·시장 지표·Java가 만드는 notes와 그 순서)는 그대로 비교한다.
 */
class GoldenEquivalenceTest {

    static final LocalDate AS_OF = LocalDate.of(2026, 10, 15);
    static final ObjectMapper OM = new ObjectMapper();
    static final SampleDataSource SAMPLE = new SampleDataSource(DataSourceConfig.resolveSampleDir("../samples/data"));
    static final Clock CLOCK = Clock.fixed(AS_OF.atTime(12, 0).atZone(ZoneId.of("Asia/Seoul")).toInstant(), ZoneId.of("Asia/Seoul"));

    static JsonNode golden(String name) throws Exception {
        try (InputStream in = GoldenEquivalenceTest.class.getResourceAsStream("/golden/" + name + ".json")) {
            return OM.readTree(in);
        }
    }

    static void assertSame(String name, Object got) throws Exception {
        List<String> d = JsonDiff.diff(golden(name), OM.valueToTree(got));
        assertThat(d).as(name + " 골든과 다른 곳").isEmpty();
    }

    @Test
    void 기업_목록_전체() throws Exception {
        CompanyService svc = new CompanyService(SAMPLE, mock(AiClient.class), CLOCK);
        assertSame("companies_all", svc.search("", 50, null, AS_OF));
    }

    @Test
    void 기업_목록_검색어_피어_5개() throws Exception {
        CompanyService svc = new CompanyService(SAMPLE, mock(AiClient.class), CLOCK);
        assertSame("companies_q_peer", svc.search("피어", 5, null, AS_OF));
    }

    @Test
    void 시장_지표() throws Exception {
        assertSame("valuation_00999001", Valuations.compute(SAMPLE, SAMPLE.resolve("999001"), AS_OF));
    }

    @ParameterizedTest
    @ValueSource(strings = {"00999001", "00888012", "00777001"})
    void 기업_상세(String corp) throws Exception {
        JsonNode g = golden("profile_" + corp);
        // AI 서버 몫(business·governance·그 안내 notes)만 골든 값으로 흉내 낸다
        List<String> aiNotes = new ArrayList<>();
        g.get("notes").forEach(n -> {
            if (n.asText().startsWith("사업 지표") || n.asText().startsWith("지배구조")) aiNotes.add(n.asText());
        });
        Map<String, Object> ins = new LinkedHashMap<>();
        ins.put("business", OM.convertValue(g.get("business"), Object.class));
        ins.put("governance", OM.convertValue(g.get("governance"), Object.class));
        ins.put("notes", aiNotes);
        AiClient ai = mock(AiClient.class);
        when(ai.insights(eq(corp), anyString(), any())).thenReturn(ins);

        CompanyService svc = new CompanyService(SAMPLE, ai, CLOCK);
        assertSame("profile_" + corp, svc.profile(corp, true, "analyst_001", List.of("DISCLOSURE_READ", "MARKET_DATA_READ"), AS_OF));
    }

    @Test
    void 상세는_AI_서버가_멈춰도_뜨고_사유를_남긴다() {
        AiClient ai = mock(AiClient.class);
        when(ai.insights(anyString(), anyString(), any()))
                .thenThrow(new ApiException(ErrorCode.AI_SERVER_UNAVAILABLE, "AI 서버 응답 없음"));
        Map<String, Object> p = new CompanyService(SAMPLE, ai, CLOCK)
                .profile("00999001", false, "analyst_001", List.of("DISCLOSURE_READ"), AS_OF);
        assertThat(p.get("business")).isNull();
        assertThat(p.get("governance")).isNull();
        assertThat(p.get("valuation")).isNull();
        assertThat(p.get("valuationNote")).isEqualTo(CompanyService.NO_MARKET_SCOPE_NOTE);
        assertThat((List<?>) p.get("notes")).anyMatch(n -> n.toString().contains("AI 서버에서 받지 못해"));
        assertThat(((Map<?, ?>) p.get("financials")).get("columns")).isEqualTo(List.of("2023", "2024", "2025"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"ALL", "KOSPI", "KOSDAQ", "KONEX"})
    void 시장_화면(String market) throws Exception {
        assertSame("market_" + market, MarketOverviewService.overview(SAMPLE, market));
    }
}
