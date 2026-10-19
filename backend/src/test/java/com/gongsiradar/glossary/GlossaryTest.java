package com.gongsiradar.glossary;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.ai.dto.GuardrailCheckResult;
import com.gongsiradar.auth.security.JwtProvider;
import com.gongsiradar.core.client.CoreSystemClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 용어집(#14): 게시된 것만 보이고, 게시는 결재자만, 자기 요청은 승인할 수 없고, 정의는 출력 필터를 거친다.
 * 공용 로컬 DB를 쓰므로 테스트마다 롤백한다(감사 로그는 별도 커넥션이라 남는다).
 */
@SpringBootTest(properties = "gongsi.data.ingested-read=false")
@AutoConfigureMockMvc
@Transactional
class GlossaryTest {

    @Autowired MockMvc mvc;
    @Autowired JwtProvider jwt;
    @Autowired ObjectMapper om;

    @MockBean AiClient aiClient;
    @MockBean CoreSystemClient core;

    static final List<String> SCOPES = List.of("DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ", "REPORT_READ");

    String junior() {
        return "Bearer " + jwt.createAccessToken("analyst_001", "주니어 김", "JUNIOR_ANALYST", SCOPES);
    }

    String senior() {
        return "Bearer " + jwt.createAccessToken("senior_001", "시니어 이", "SENIOR_MANAGER", SCOPES);
    }

    @BeforeEach
    void safe() {
        when(aiClient.outputCheck(any(), any(), any()))
                .thenReturn(new GuardrailCheckResult(true, "SAFE", List.of(), null, false, false));
    }

    long create(String auth, String term, String definition) throws Exception {
        String body = om.writeValueAsString(Map.of("term", term, "aliases", List.of("별칭 " + term),
                "definition", definition, "usageNote", "테스트"));
        String res = mvc.perform(post("/api/glossary").header("Authorization", auth)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("DRAFT"))
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        return om.readTree(res).at("/data/id").asLong();
    }

    boolean publishedContains(String term) throws Exception {
        String res = mvc.perform(get("/api/glossary").header("Authorization", junior()))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        for (JsonNode n : om.readTree(res).get("data")) {
            if (term.equals(n.get("term").asText())) return true;
        }
        return false;
    }

    @Test
    void 초안은_보이지_않고_결재자가_승인해야_게시된다() throws Exception {
        String term = "테스트용어-" + UUID.randomUUID();
        long id = create(junior(), term, "시험용 정의입니다.");
        assertThat(publishedContains(term)).isFalse();

        mvc.perform(post("/api/glossary/" + id + "/submit").header("Authorization", junior()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("PENDING"));
        assertThat(publishedContains(term)).isFalse();

        mvc.perform(post("/api/glossary/" + id + "/approve").header("Authorization", junior()))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/glossary/" + id + "/approve").header("Authorization", senior())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"확인\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("PUBLISHED"))
                .andExpect(jsonPath("$.data.reviewedBy").value("senior_001"));
        assertThat(publishedContains(term)).isTrue();
    }

    @Test
    void 자기가_검토를_요청한_용어는_승인할_수_없다() throws Exception {
        long id = create(senior(), "테스트용어-" + UUID.randomUUID(), "시험용 정의입니다.");
        mvc.perform(post("/api/glossary/" + id + "/submit").header("Authorization", senior()))
                .andExpect(status().isOk());
        mvc.perform(post("/api/glossary/" + id + "/approve").header("Authorization", senior()))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("SELF_APPROVAL_FORBIDDEN"));
    }

    @Test
    void 금지_표현이_있으면_검토_요청이_막힌다() throws Exception {
        long id = create(junior(), "테스트용어-" + UUID.randomUUID(), "지금이 투자 적기입니다.");
        when(aiClient.outputCheck(any(), any(), any()))
                .thenReturn(new GuardrailCheckResult(false, "BLOCKED", List.of("가치판단"), null, true, false));
        mvc.perform(post("/api/glossary/" + id + "/submit").header("Authorization", junior()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("GUARDRAIL_BLOCKED"));
        mvc.perform(get("/api/glossary/manage").header("Authorization", junior()))
                .andExpect(jsonPath("$.data[?(@.id == " + id + ")].status").value("DRAFT"));
    }

    @Test
    void 반려는_사유가_필요하고_반려된_용어는_고쳐서_다시_요청한다() throws Exception {
        String term = "테스트용어-" + UUID.randomUUID();
        long id = create(junior(), term, "시험용 정의입니다.");
        mvc.perform(post("/api/glossary/" + id + "/submit").header("Authorization", junior())).andExpect(status().isOk());
        mvc.perform(post("/api/glossary/" + id + "/reject").header("Authorization", senior())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/api/glossary/" + id + "/reject").header("Authorization", senior())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"예시를 넣어 주세요\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("REJECTED"))
                .andExpect(jsonPath("$.data.reviewComment").value("예시를 넣어 주세요"));

        String edit = om.writeValueAsString(Map.of("term", term, "definition", "고친 정의입니다. 예: 1만 원 중 1,310원."));
        mvc.perform(put("/api/glossary/" + id).header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON).content(edit))
                .andExpect(status().isOk());
        mvc.perform(post("/api/glossary/" + id + "/submit").header("Authorization", junior()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("PENDING"));
    }

    @Test
    void 같은_표제어는_두_번_만들_수_없고_다른_사람의_초안은_고칠_수_없다() throws Exception {
        String term = "테스트용어-" + UUID.randomUUID();
        long id = create(junior(), term, "시험용 정의입니다.");
        mvc.perform(post("/api/glossary").header("Authorization", senior()).contentType(MediaType.APPLICATION_JSON)
                        .content(om.writeValueAsString(Map.of("term", term, "definition", "중복"))))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("GLOSSARY_CONFLICT"));
        String other = "Bearer " + jwt.createAccessToken("analyst_002", "주니어 박", "JUNIOR_ANALYST", SCOPES);
        mvc.perform(put("/api/glossary/" + id).header("Authorization", other).contentType(MediaType.APPLICATION_JSON)
                        .content(om.writeValueAsString(Map.of("term", term, "definition", "남의 초안"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void 초기_용어가_게시되어_있다() throws Exception {
        assertThat(publishedContains("TTM")).isTrue();
        assertThat(publishedContains("지배주주 순이익")).isTrue();
    }
}
