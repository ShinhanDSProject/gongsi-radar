package com.gongsiradar.report.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.gongsiradar.report.AnalysisReport;
import com.gongsiradar.report.ApprovalStatus;

import java.time.LocalDateTime;

/**
 * CONTRACT §3.3 ReportDto. {@code body}는 RadarReport JSON을 그대로 싣는다.
 * <p>
 * 계약 필드 뒤에 {@code userId}·{@code corpCode}·{@code corpName}을 덧붙였다(목록 화면용, 추가 필드만).
 */
public record ReportDto(
        Long id,
        Long requestId,
        String title,
        String summary,
        ApprovalStatus approvalStatus,
        String publicationId,
        JsonNode body,
        String disclaimer,
        LocalDateTime createdAt,
        LocalDateTime updatedAt,
        String userId,
        String corpCode,
        String corpName
) {
    public static ReportDto of(AnalysisReport r, JsonNode body, String userId, String corpCode, String corpName) {
        return new ReportDto(r.getId(), r.getRequestId(), r.getTitle(), r.getSummary(),
                r.getApprovalStatus(), r.getPublicationId(), body, r.getDisclaimer(),
                r.getCreatedAt(), r.getUpdatedAt(), userId, corpCode, corpName);
    }
}
