package com.gongsiradar.analysis.dto;

import com.gongsiradar.analysis.repository.AnalysisRequest;
import com.gongsiradar.analysis.repository.AnalysisRequestStatus;

import java.time.LocalDateTime;
import java.util.List;

public record AnalysisRequestDto(
        Long id,
        String userId,
        String company,
        String corpCode,
        String corpName,
        Integer bsnsYear,
        String reprtCode,
        String query,
        List<String> scope,
        AnalysisRequestStatus status,
        String jobId,
        Long reportId,
        boolean demoFaultInjection,
        LocalDateTime createdAt,
        LocalDateTime startedAt,
        LocalDateTime finishedAt
) {
    public static AnalysisRequestDto of(AnalysisRequest r, Long reportId) {
        return new AnalysisRequestDto(r.getId(), r.getUserId(), r.getCompany(),
                r.getCorpCode(), r.getCorpName(), r.getBsnsYear(), r.getReprtCode(),
                r.getQuery(), r.getScope() == null ? List.of() : r.getScope(),
                r.getStatus(), r.getJobId(), reportId, r.isDemoFaultInjection(),
                r.getCreatedAt(), r.getStartedAt(), r.getFinishedAt());
    }
}
