package com.gongsiradar.publication.dto;

import com.gongsiradar.publication.PublicationQueue;

import java.time.LocalDateTime;

/** CONTRACT §3.4 PublicationDto. */
public record PublicationDto(
        String publicationId,
        Long reportId,
        String corpCode,
        String corpName,
        String periodLabel,
        String title,
        Integer version,
        String supersedesId,
        String contentHash,
        String status,
        String submittedBy,
        String decidedBy,
        LocalDateTime decidedAt,
        String comment,
        LocalDateTime createdAt,
        LocalDateTime decisionRequiredBy
) {
    public static PublicationDto from(PublicationQueue q) {
        return new PublicationDto(
                q.getPublicationId(), q.getReportId(), q.getCorpCode(), q.getCorpName(),
                q.getPeriodLabel(), q.getTitle(), q.getVersion(), q.getSupersedesId(),
                q.getContentHash(), q.getStatus(), q.getSubmittedBy(), q.getDecidedBy(),
                q.getDecidedAt(), q.getComment(), q.getCreatedAt(), q.getDecisionRequiredBy());
    }
}
