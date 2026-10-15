package com.gongsiradar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.ai.AiClient;
import com.gongsiradar.ai.dto.AiJobStatus;
import com.gongsiradar.ai.dto.GuardrailCheckResult;
import com.gongsiradar.analysis.AnalysisRequest;
import com.gongsiradar.analysis.AnalysisRequestRepository;
import com.gongsiradar.analysis.AnalysisRequestStatus;
import com.gongsiradar.auth.JwtProvider;
import com.gongsiradar.common.ApiException;
import com.gongsiradar.common.ErrorCode;
import com.gongsiradar.common.Hashing;
import com.gongsiradar.core.CoreSystemClient;
import com.gongsiradar.core.dto.CorePublicationDto;
import com.gongsiradar.publication.PublicationQueue;
import com.gongsiradar.publication.PublicationQueueRepository;
import com.gongsiradar.report.AnalysisReport;
import com.gongsiradar.report.AnalysisReportRepository;
import com.gongsiradar.report.ApprovalStatus;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 분석 → 리포트 → 발행 결재 흐름. AI 서버·Core Zone은 Mock으로 바꾸고 MariaDB는 실제로 쓴다.
 * <p>
 * 테스트마다 트랜잭션을 롤백한다(gongsi_app 계정에는 DELETE 권한이 없어 지울 수 없다).
 * 감사 로그는 별도 커넥션(gongsi_audit)으로 쓰므로 롤백되지 않고 남는다 — append-only라 그게 맞다.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class WorkflowTest {

    static final String REPORT_JSON = """
            {"title":"샘플소재㈜ 2025 사업보고서 공시 비교","summary":"전년 대비 소송 항목이 늘었다.",
             "meta":{"company":{"corp_code":"00999001","corp_name":"샘플소재㈜"},"disclaimer":"투자 권유가 아닙니다."},
             "changes":[{"id":"chg-001","summary":"원래 요약"}],
             "relations":[{"account_key":"revenue","statement":"원래 문장"}],
             "review":{"status":"검토 대기","reviewer":null,"decided_at":null,"comment":null,"events":[]}}
            """;

    @Autowired MockMvc mvc;
    @Autowired JwtProvider jwt;
    @Autowired ObjectMapper om;
    @Autowired AnalysisRequestRepository requests;
    @Autowired AnalysisReportRepository reports;
    @Autowired PublicationQueueRepository queue;

    @MockBean AiClient aiClient;
    @MockBean CoreSystemClient core;

    static final List<String> JUNIOR_SCOPES = List.of("DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ", "REPORT_READ");
    static final List<String> SENIOR_SCOPES = List.of("DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ",
            "REPORT_READ", "REPORT_WRITE", "PUBLICATION_READ");

    String junior() {
        return "Bearer " + jwt.createAccessToken("analyst_001", "주니어 김", "JUNIOR_ANALYST", JUNIOR_SCOPES);
    }

    String junior2() {
        return "Bearer " + jwt.createAccessToken("analyst_002", "주니어 박", "JUNIOR_ANALYST", JUNIOR_SCOPES);
    }

    String senior() {
        return "Bearer " + jwt.createAccessToken("senior_001", "시니어 이", "SENIOR_MANAGER", SENIOR_SCOPES);
    }

    AnalysisRequest newRequest(String owner, AnalysisRequestStatus status) {
        return requests.saveAndFlush(AnalysisRequest.builder()
                .userId(owner).company("999001").corpCode("00999001").corpName("샘플소재㈜")
                .bsnsYear(2025).reprtCode("11011").scope(List.of("DISCLOSURE_READ"))
                .status(status).jobId("job-" + UUID.randomUUID()).build());
    }

    AnalysisReport newReport(AnalysisRequest req, ApprovalStatus status) {
        return reports.saveAndFlush(AnalysisReport.builder()
                .requestId(req.getId()).title("t").summary("s").bodyJson(REPORT_JSON.strip())
                .disclaimer("d").approvalStatus(status).build());
    }

    PublicationQueue newPending(AnalysisReport report, String submittedBy) {
        return queue.saveAndFlush(PublicationQueue.builder()
                .publicationId("PUB-" + UUID.randomUUID()).reportId(report.getId())
                .idempotencyKey(UUID.randomUUID().toString())
                .corpCode("00999001").corpName("샘플소재㈜").periodLabel("2025 사업보고서").title("t")
                .contentHash(Hashing.sha256Hex(report.getBodyJson())).version(1)
                .submittedBy(submittedBy).status(PublicationQueue.PENDING).build());
    }

    // ───────── 발행 결재 ─────────

    @Test
    void Junior는_발행을_승인할_수_없다_403() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.PENDING);
        PublicationQueue pub = newPending(report, "analyst_001");

        mvc.perform(post("/api/publications/" + pub.getPublicationId() + "/approve")
                        .header("Authorization", junior2()))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("FORBIDDEN"));
        verifyNoInteractions(core);
    }

    @Test
    void 자기가_요청한_발행은_승인할_수_없다_SELF_APPROVAL_FORBIDDEN() throws Exception {
        AnalysisReport report = newReport(newRequest("senior_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.PENDING);
        PublicationQueue pub = newPending(report, "senior_001");

        mvc.perform(post("/api/publications/" + pub.getPublicationId() + "/approve")
                        .header("Authorization", senior())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"ok\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("SELF_APPROVAL_FORBIDDEN"));
        // Core Zone까지 가지 않는다
        verifyNoInteractions(core);
    }

    @Test
    void 발행_요청은_SUBMITTING을_먼저_저장하고_Core에_멱등성_키를_보낸다() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.DRAFT);
        String hash = Hashing.sha256Hex(report.getBodyJson());
        when(core.submitPublication(eq(report.getId()), eq("00999001"), eq("샘플소재㈜"), eq("2025 사업보고서"),
                anyString(), eq(hash), eq("analyst_001"), any(), anyString()))   // supersedesId: 공유 DB에 이전 발행이 있으면 채워진다
                .thenAnswer(inv -> {
                    // Core를 부르는 시점에 이미 같은 키로 SUBMITTING 행이 있어야 한다
                    String key = inv.getArgument(8);
                    assertThat(queue.findAll()).anyMatch(q -> key.equals(q.getIdempotencyKey())
                            && PublicationQueue.SUBMITTING.equals(q.getStatus()));
                    return new CorePublicationDto("PUB-T1", report.getId(), null, null, null, null, hash, 1, null,
                            "PENDING", "analyst_001", null, null, null, "2026-10-15T12:00:00+09:00",
                            "2026-10-16T12:00:00+09:00", false);
                });

        mvc.perform(post("/api/publications").header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reportId\":" + report.getId() + "}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.publicationId").value("PUB-T1"))
                .andExpect(jsonPath("$.data.status").value("PENDING"))
                .andExpect(jsonPath("$.data.periodLabel").value("2025 사업보고서"))
                .andExpect(jsonPath("$.data.contentHash").value(hash));

        AnalysisReport after = reports.findById(report.getId()).orElseThrow();
        assertThat(after.getApprovalStatus()).isEqualTo(ApprovalStatus.PENDING);
        assertThat(after.getPublicationId()).isEqualTo("PUB-T1");
    }

    @Test
    void 승인하면_리포트가_APPROVED가_되고_review_status가_승인됨() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.PENDING);
        PublicationQueue pub = newPending(report, "analyst_001");
        when(core.approvePublication(pub.getPublicationId(), "senior_001", pub.getContentHash()))
                .thenReturn(new CorePublicationDto(pub.getPublicationId(), report.getId(), null, null, null, null,
                        pub.getContentHash(), 1, null, "PUBLISHED", "analyst_001", "senior_001",
                        "2026-10-15T13:00:00+09:00", "2026-10-15T13:00:00+09:00", null, null, false));

        mvc.perform(post("/api/publications/" + pub.getPublicationId() + "/approve")
                        .header("Authorization", senior())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"확인함\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("PUBLISHED"))
                .andExpect(jsonPath("$.data.decidedBy").value("senior_001"));

        AnalysisReport after = reports.findById(report.getId()).orElseThrow();
        assertThat(after.getApprovalStatus()).isEqualTo(ApprovalStatus.APPROVED);
        JsonNode review = om.readTree(after.getBodyJson()).path("review");
        assertThat(review.path("status").asText()).isEqualTo("승인됨");
        assertThat(review.path("reviewer").asText()).isEqualTo("senior_001");
        assertThat(review.path("events").get(0).path("action").asText()).isEqualTo("승인");
    }

    @Test
    void Core가_409로_거절하면_CORE_PUBLICATION_REJECTED() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.PENDING);
        PublicationQueue pub = newPending(report, "analyst_001");
        when(core.approvePublication(anyString(), anyString(), anyString()))
                .thenThrow(new ApiException(ErrorCode.CORE_PUBLICATION_REJECTED, "Core Zone이 발행을 거절했다",
                        Map.of("error", "CONTENT_CHANGED")));

        mvc.perform(post("/api/publications/" + pub.getPublicationId() + "/approve")
                        .header("Authorization", senior()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("CORE_PUBLICATION_REJECTED"))
                .andExpect(jsonPath("$.error.details.error").value("CONTENT_CHANGED"));
    }

    // ───────── 리포트 수정 ─────────

    @Test
    void 발행_요청된_리포트는_수정할_수_없다_REPORT_LOCKED() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.PENDING);

        mvc.perform(post("/api/reports/" + report.getId() + "/edits").header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"itemId\":\"chg-001\",\"value\":\"새 요약\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("REPORT_LOCKED"));
        verify(aiClient, never()).outputCheck(anyString(), anyString(), any());
    }

    @Test
    void 출력_가드레일이_막으면_422이고_본문은_그대로() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.DRAFT);
        when(aiClient.outputCheck(anyString(), eq("analyst_001"), any()))
                .thenReturn(new GuardrailCheckResult(false, "BLOCKED", List.of("BANNED:매수"), null, true, false));

        mvc.perform(post("/api/reports/" + report.getId() + "/edits").header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"itemId\":\"chg-001\",\"value\":\"지금 매수하세요\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("GUARDRAIL_BLOCKED"));

        assertThat(reports.findById(report.getId()).orElseThrow().getBodyJson()).isEqualTo(REPORT_JSON.strip());
    }

    @Test
    void 수정이_통과하면_changes_summary를_고치고_review_events에_남긴다() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.DRAFT);
        when(aiClient.outputCheck(anyString(), anyString(), any()))
                .thenReturn(new GuardrailCheckResult(true, "SAFE", List.of(), "검토자가 고친 요약", false, false));

        mvc.perform(post("/api/reports/" + report.getId() + "/edits").header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"itemId\":\"chg-001\",\"value\":\"검토자가 고친 요약\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.body.changes[0].summary").value("검토자가 고친 요약"))
                .andExpect(jsonPath("$.data.body.review.events[0].action").value("수정"))
                .andExpect(jsonPath("$.data.body.review.events[0].item_id").value("chg-001"))
                .andExpect(jsonPath("$.data.body.review.events[0].actor").value("analyst_001"));

        mvc.perform(post("/api/reports/" + report.getId() + "/edits").header("Authorization", junior())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"itemId\":\"revenue\",\"value\":\"검토자가 고친 요약\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.body.relations[0].statement").value("검토자가 고친 요약"));
    }

    @Test
    void Junior는_남의_리포트를_볼_수_없다() throws Exception {
        AnalysisReport report = newReport(newRequest("analyst_001", AnalysisRequestStatus.COMPLETED), ApprovalStatus.DRAFT);
        mvc.perform(get("/api/reports/" + report.getId()).header("Authorization", junior2()))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/reports/" + report.getId()).header("Authorization", senior()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.body.meta.company.corp_code").value("00999001"));
    }

    // ───────── 분석 요청 ─────────

    @Test
    void Job이_COMPLETED면_리포트를_저장하고_회사를_확정한다() throws Exception {
        AnalysisRequest req = requests.saveAndFlush(AnalysisRequest.builder()
                .userId("analyst_001").company("샘플소재").bsnsYear(2025).reprtCode("11011")
                .scope(List.of("DISCLOSURE_READ")).status(AnalysisRequestStatus.RUNNING).jobId("job-c1").build());
        Map<String, Object> report = om.readValue(REPORT_JSON, Map.class);
        when(aiClient.getJob(eq("job-c1"), anyString(), any()))
                .thenReturn(new AiJobStatus("job-c1", "COMPLETED", 1.0, "DONE", Map.of("report", report), List.of()));

        mvc.perform(get("/api/analysis-requests/" + req.getId() + "/status").header("Authorization", junior()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("COMPLETED"))
                .andExpect(jsonPath("$.data.corpCode").value("00999001"))
                .andExpect(jsonPath("$.data.corpName").value("샘플소재㈜"))
                .andExpect(jsonPath("$.data.reportId").isNumber());

        AnalysisReport saved = reports.findByRequestId(req.getId()).orElseThrow();
        assertThat(saved.getTitle()).isEqualTo("샘플소재㈜ 2025 사업보고서 공시 비교");
        assertThat(saved.getSummary()).isEqualTo("전년 대비 소송 항목이 늘었다.");
        assertThat(saved.getDisclaimer()).isEqualTo("투자 권유가 아닙니다.");
        assertThat(saved.getApprovalStatus()).isEqualTo(ApprovalStatus.DRAFT);
    }

    @Test
    void 입력_가드레일이_막으면_요청이_BLOCKED가_된다() throws Exception {
        AnalysisRequest req = requests.saveAndFlush(AnalysisRequest.builder()
                .userId("analyst_001").company("999001").bsnsYear(2025).reprtCode("11011")
                .scope(List.of("DISCLOSURE_READ")).status(AnalysisRequestStatus.CREATED).build());
        when(aiClient.startAnalysis(any(), any()))
                .thenThrow(new ApiException(ErrorCode.GUARDRAIL_BLOCKED, "차단", Map.of("error", "GUARDRAIL_BLOCKED")));

        mvc.perform(post("/api/analysis-requests/" + req.getId() + "/execute").header("Authorization", junior()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("GUARDRAIL_BLOCKED"));

        assertThat(requests.findById(req.getId()).orElseThrow().getStatus()).isEqualTo(AnalysisRequestStatus.BLOCKED);
    }

    @Test
    void Junior_목록은_자기_것만_Senior는_전체() throws Exception {
        AnalysisRequest mine = newRequest("analyst_001", AnalysisRequestStatus.CREATED);
        AnalysisRequest other = newRequest("analyst_002", AnalysisRequestStatus.CREATED);

        String juniorList = mvc.perform(get("/api/analysis-requests?size=100").header("Authorization", junior()))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        List<Integer> juniorIds = com.jayway.jsonpath.JsonPath.read(juniorList, "$.data.content[*].id");
        assertThat(juniorIds).contains(mine.getId().intValue()).doesNotContain(other.getId().intValue());

        String seniorList = mvc.perform(get("/api/analysis-requests?size=100").header("Authorization", senior()))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        List<Integer> seniorIds = com.jayway.jsonpath.JsonPath.read(seniorList, "$.data.content[*].id");
        assertThat(seniorIds).contains(mine.getId().intValue(), other.getId().intValue());
    }

    @Test
    void 시장_화면은_필터를_먼저_검사하고_AI_서버로_프록시한다() throws Exception {
        when(aiClient.market(eq("KOSDAQ"), eq("analyst_001"), anyList()))
                .thenReturn(java.util.Map.of("market", "KOSDAQ", "sample", true));
        mvc.perform(get("/api/market").param("market", "kosdaq").header("Authorization", junior()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.market").value("KOSDAQ"));
        // 잘못된 값은 AI 서버까지 가지 않는다
        mvc.perform(get("/api/market").param("market", "NYSE").header("Authorization", junior()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        verify(aiClient, times(1)).market(anyString(), anyString(), anyList());
    }
}
