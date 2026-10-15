package com.gongsiradar.core.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Core Zone 발행 원장이 돌려주는 발행 건 한 개. CONTRACT §5. */
@JsonIgnoreProperties(ignoreUnknown = true) // 역직렬화시 존재하지 않는 속성 예외 방지
public record CorePublicationDto(
        String publicationId,
        Long reportId,
        String corpCode,
        String corpName,
        String periodLabel,
        String title,
        String contentHash,
        Integer version,
        String supersedesId,
        String status,            // PENDING, PUBLISHED, REJECTED, EXPIRED, FAILED, SUPERSEDED
        String submittedBy,
        String decidedBy,
        String decidedAt,
        String publishedAt,
        String createdAt,
        String decisionRequiredBy,
        Boolean duplicate         // 같은 멱등성 키 재전송이면 true
) {}
