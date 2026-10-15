package com.gongsiradar.audit.dto;

import com.gongsiradar.audit.AuditLog;

import java.time.LocalDateTime;

public record AuditLogDto(
        Long id,
        String type,
        String requestUid,
        String userId,
        String agentId,
        Long requestId,
        String payloadJson,
        LocalDateTime createdAt
) {
    public static AuditLogDto from(AuditLog e) {
        return new AuditLogDto(e.getId(), e.getType(), e.getRequestUid(), e.getUserId(),
                e.getAgentId(), e.getRequestId(), e.getPayloadJson(), e.getCreatedAt());
    }
}
