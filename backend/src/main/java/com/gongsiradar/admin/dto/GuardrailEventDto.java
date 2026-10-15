package com.gongsiradar.admin.dto;

import com.gongsiradar.admin.repository.GuardrailEvent;

import java.time.LocalDateTime;

public record GuardrailEventDto(
        Long id,
        String type,
        String severity,
        String requestUid,
        String userId,
        String detectedIssues,
        boolean blocked,
        LocalDateTime createdAt
) {
    public static GuardrailEventDto from(GuardrailEvent e) {
        return new GuardrailEventDto(e.getId(), e.getType(), e.getSeverity(),
                e.getRequestUid(), e.getUserId(), e.getDetectedIssues(),
                Boolean.TRUE.equals(e.getBlocked()), e.getCreatedAt());
    }
}
