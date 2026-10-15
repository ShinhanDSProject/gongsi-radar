package com.gongsiradar.internal;

import com.gongsiradar.ai.client.AiClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.ByteArrayInputStream;
import java.util.zip.ZipInputStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 내부 데이터 API(CONTRACT §11.2). 샘플 원천 + 적재 DB(MariaDB 3307)를 그대로 읽는다. */
@SpringBootTest
@AutoConfigureMockMvc
class InternalDataApiTest {

    static final String KEY = "dev-data-internal-key";

    @Autowired MockMvc mvc;
    @MockBean AiClient aiClient;

    @Test
    void 키가_없거나_틀리면_401_detail() throws Exception {
        mvc.perform(get("/internal/data/companies"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("X-Data-Origin", "sample"))
                .andExpect(jsonPath("$.detail").isString());
        mvc.perform(get("/internal/data/companies").header("X-Internal-API-Key", "dev-ai-internal-key"))
                .andExpect(status().isUnauthorized());
        // JWT로도 들어올 수 없다(JWT 경로가 아니다)
        mvc.perform(get("/internal/data/companies").header("Authorization", "Bearer x"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void 없는_데이터는_404_detail이고_원천_헤더가_붙는다() throws Exception {
        mvc.perform(get("/internal/data/financials").header("X-Internal-API-Key", KEY)
                        .param("corpCode", "00999001").param("bsnsYear", "2019").param("reprtCode", "11011"))
                .andExpect(status().isNotFound())
                .andExpect(header().string("X-Data-Origin", "sample"))
                .andExpect(jsonPath("$.detail", containsString("013")));
        mvc.perform(get("/internal/data/companies/resolve").header("X-Internal-API-Key", KEY).param("q", "없는회사"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").isString());
        mvc.perform(get("/internal/data/documents/20990101000001").header("X-Internal-API-Key", KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").isString());
    }

    @Test
    void 재무는_원천_모양_fs_div_list() throws Exception {
        mvc.perform(get("/internal/data/financials").header("X-Internal-API-Key", KEY).header("X-User-Id", "analyst_001")
                        .param("corpCode", "00999001").param("bsnsYear", "2025").param("reprtCode", "11011"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Data-Origin", "sample"))
                .andExpect(jsonPath("$.fs_div").value("CFS"))
                .andExpect(jsonPath("$.list[0].rcept_no").value("20260317000388"))
                .andExpect(jsonPath("$.list[*].account_nm", hasItem("매출액")))
                .andExpect(jsonPath("$.list[?(@.account_nm == '매출액')].thstrm_amount", hasItem("1012000000000")));
    }

    @Test
    void 회사_찾기와_목록과_공시() throws Exception {
        mvc.perform(get("/internal/data/companies/resolve").header("X-Internal-API-Key", KEY).param("q", "999001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.corp_code").value("00999001"))
                .andExpect(jsonPath("$.market").value("KOSDAQ"))
                .andExpect(jsonPath("$.induty_code").value("20129"));
        mvc.perform(get("/internal/data/companies").header("X-Internal-API-Key", KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(46)));
        mvc.perform(get("/internal/data/filings").header("X-Internal-API-Key", KEY).param("corpCode", "00999001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].reprt_code").value("11012"))
                .andExpect(jsonPath("$[1].hasDocument").value(true));
        mvc.perform(get("/internal/data/report").header("X-Internal-API-Key", KEY)
                        .param("corpCode", "00999001").param("bsnsYear", "2025").param("reprtCode", "11011"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rcept_no").value("20260317000388"))
                .andExpect(jsonPath("$.url", containsString("rcpNo=20260317000388")));
    }

    @Test
    void 원문은_zip_바이트() throws Exception {
        MvcResult r = mvc.perform(get("/internal/data/documents/20260317000388").header("X-Internal-API-Key", KEY))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Type", "application/zip"))
                .andExpect(header().string("X-Data-Origin", "sample"))
                .andReturn();
        byte[] body = r.getResponse().getContentAsByteArray();
        assertThat(new String(body, 0, 2)).isEqualTo("PK");
        try (ZipInputStream z = new ZipInputStream(new ByteArrayInputStream(body))) {
            assertThat(z.getNextEntry()).isNotNull();
        }
    }

    @Test
    void 시세_피어_소송_지배구조() throws Exception {
        mvc.perform(get("/internal/data/market/999001").header("X-Internal-API-Key", KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].basDt").value("20261014"))
                .andExpect(jsonPath("$.items[0].clpr").value("60700"))
                .andExpect(jsonPath("$.items", hasSize(262)));
        mvc.perform(get("/internal/data/peers").header("X-Internal-API-Key", KEY)
                        .param("corpCode", "00999001").param("bsnsYear", "2025").param("reprtCode", "11011"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.list", hasSize(116)));
        mvc.perform(get("/internal/data/lawsuits").header("X-Internal-API-Key", KEY)
                        .param("corpCode", "00999001").param("bgn", "20250101").param("end", "20251231"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.list", hasSize(1)));
        mvc.perform(get("/internal/data/governance").header("X-Internal-API-Key", KEY)
                        .param("corpCode", "00999001").param("bsnsYear", "2025").param("reprtCode", "11011"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rcept_no").value("20260317000388"))
                .andExpect(jsonPath("$.shareholders[0].nm").value("샘플홀딩스㈜"));
    }

    @Test
    void 내부_API는_api_경로의_JWT와_섞이지_않는다() throws Exception {
        mvc.perform(get("/api/companies").header("X-Internal-API-Key", KEY))
                .andExpect(status().isUnauthorized());
    }
}
