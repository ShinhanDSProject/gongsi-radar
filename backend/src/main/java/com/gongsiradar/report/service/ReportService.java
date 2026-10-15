package com.gongsiradar.report.service;

import com.gongsiradar.report.repository.AnalysisReport;
import com.gongsiradar.report.repository.ApprovalStatus;
import com.gongsiradar.report.repository.AnalysisReportRepository;
import com.gongsiradar.report.support.ReportBody;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.ai.dto.GuardrailCheckResult;
import com.gongsiradar.analysis.repository.AnalysisRequest;
import com.gongsiradar.analysis.repository.AnalysisRequestRepository;
import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.report.dto.EditRequest;
import com.gongsiradar.report.dto.ReportDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 분석 리포트 조회·검토자 수정.
 * <p>
 * 검토자가 고친 문구도 LLM이 쓴 문장과 똑같이 출력 가드레일을 통과해야 리포트에 남는다.
 * "사람이 썼으니 괜찮다"는 예외를 두면 투자 권유 문구가 그 틈으로 들어온다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ReportService {

    private static final Map<String, String> REPRT_NAMES = Map.of(
            "11011", "사업보고서", "11012", "반기보고서",
            "11013", "1분기보고서", "11014", "3분기보고서");

    private final AnalysisReportRepository reportRepository;
    private final AnalysisRequestRepository requestRepository;
    private final ReportBody reportBody;
    private final AiClient aiClient;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public Page<ReportDto> list(String userId, boolean senior, ApprovalStatus status, Pageable pageable) {
        Page<AnalysisReport> page = reportRepository.search(status, senior ? null : userId, pageable);
        List<Long> requestIds = page.getContent().stream().map(AnalysisReport::getRequestId).toList();
        Map<Long, AnalysisRequest> requests = requestRepository.findAllById(requestIds).stream()
                .collect(Collectors.toMap(AnalysisRequest::getId, Function.identity()));
        return page.map(r -> toDto(r, requests.get(r.getRequestId())));
    }

    @Transactional(readOnly = true)
    public ReportDto get(Long id, String userId, boolean senior) {
        AnalysisReport report = findReport(id);
        AnalysisRequest request = checkAccess(report, userId, senior);
        return toDto(report, request);
    }

    /**
     * 검토자 문구 수정. 순서가 중요하다 — 잠금 확인 → 출력 가드레일 → 본문 수정 → 감사.
     * 가드레일이 통과시킨 문구(마스킹된 filteredText)를 저장한다.
     */
    @Transactional
    public ReportDto edit(Long id, String userId, boolean senior, EditRequest req) {
        AnalysisReport report = findReport(id);
        AnalysisRequest request = checkAccess(report, userId, senior);

        if (report.getApprovalStatus().locked()) {
            throw new ApiException(ErrorCode.REPORT_LOCKED,
                    "발행 요청 이후에는 리포트를 수정할 수 없습니다",
                    Map.of("approvalStatus", report.getApprovalStatus().name()));
        }

        GuardrailCheckResult check = aiClient.outputCheck(req.value(), userId,
                Map.of("kind", "report_edit", "reportId", report.getId(), "itemId", req.itemId()));
        if (check == null || check.blocked()) {
            Map<String, Object> payload = new HashMap<>();
            payload.put("stage", "REPORT_EDIT");
            payload.put("reportId", report.getId());
            payload.put("itemId", req.itemId());
            payload.put("riskLevel", check == null ? null : check.riskLevel());
            payload.put("detectedIssues", check == null ? List.of() : check.detectedIssues());
            auditService.record("GUARDRAIL_BLOCKED", userId, null, report.getRequestId(), payload);
            Map<String, Object> details = new HashMap<>();
            details.put("riskLevel", check == null ? null : check.riskLevel());
            details.put("detectedIssues", check == null ? List.of() : check.detectedIssues());
            throw new ApiException(ErrorCode.GUARDRAIL_BLOCKED,
                    "수정한 문구에 사용할 수 없는 표현이 포함되어 있습니다", details);
        }
        String value = (check.filteredText() != null && !check.filteredText().isBlank())
                ? check.filteredText() : req.value();

        ObjectNode body = reportBody.parse(report.getBodyJson());
        ReportBody.Edit edit = reportBody.applyEdit(body, req.itemId(), value);
        String label = edit.field() == ReportBody.EditedField.CHANGE_SUMMARY ? "변경 요약 수정" : "관계 문장 수정";
        reportBody.appendEvent(body, userId, "수정", req.itemId(),
                label + " (이전: " + abbreviate(edit.previous(), 200) + ")");
        report.updateBody(reportBody.write(body));

        auditService.record("REPORT_EDITED", userId, null, report.getRequestId(), Map.of(
                "reportId", report.getId(), "itemId", req.itemId(),
                "field", edit.field().name(),
                "riskLevel", check.riskLevel() == null ? "" : check.riskLevel()));
        return toDto(report, request);
    }

    /**
     * AI Job이 끝났을 때 리포트를 저장한다. 같은 요청에 이미 있으면 그대로 둔다(폴링이 겹쳐도 한 건).
     * title·summary는 리포트 래퍼 필드(CONTRACT §6.1), disclaimer는 meta.disclaimer에서 가져온다.
     */
    @Transactional
    public AnalysisReport saveFromAiResult(AnalysisRequest request, Object reportObj) {
        return reportRepository.findByRequestId(request.getId()).orElseGet(() -> {
            JsonNode report = objectMapper.valueToTree(reportObj);
            String title = ReportBody.text(report, "title");
            if (title == null) {
                title = (request.getCorpName() != null ? request.getCorpName() : request.getCompany())
                        + " " + periodLabel(request.getBsnsYear(), request.getReprtCode()) + " 공시 비교 리포트";
            }
            AnalysisReport saved = reportRepository.save(AnalysisReport.builder()
                    .requestId(request.getId())
                    .title(abbreviate(title, 500))
                    .summary(ReportBody.text(report, "summary"))
                    .bodyJson(reportBody.write(report))
                    .disclaimer(ReportBody.text(report.path("meta"), "disclaimer"))
                    .approvalStatus(ApprovalStatus.DRAFT)
                    .build());
            log.info("analysis_report 저장 request={} report={}", request.getId(), saved.getId());
            return saved;
        });
    }

    /** "2025 사업보고서". 발행 원장의 기간 표시와 같은 규칙이다. */
    public static String periodLabel(Integer bsnsYear, String reprtCode) {
        return bsnsYear + " " + REPRT_NAMES.getOrDefault(reprtCode, reprtCode);
    }

    // ── 내부 ──

    AnalysisReport findReport(Long id) {
        return reportRepository.findById(id)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트를 찾을 수 없음"));
    }

    /** Junior는 자기 분석 요청의 리포트만, Senior는 전체. */
    AnalysisRequest checkAccess(AnalysisReport report, String userId, boolean senior) {
        AnalysisRequest request = requestRepository.findById(report.getRequestId())
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트의 분석 요청이 없음"));
        if (!senior && !request.getUserId().equals(userId)) {
            throw new ApiException(ErrorCode.FORBIDDEN, "타인의 리포트에 접근 불가");
        }
        return request;
    }

    ReportDto toDto(AnalysisReport r, AnalysisRequest request) {
        return ReportDto.of(r, reportBody.parseLenient(r.getBodyJson()),
                request == null ? null : request.getUserId(),
                request == null ? null : request.getCorpCode(),
                request == null ? null : request.getCorpName());
    }

    private static String abbreviate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max - 1) + "…";
    }
}
