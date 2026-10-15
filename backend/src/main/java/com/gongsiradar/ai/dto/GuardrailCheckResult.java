package com.gongsiradar.ai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

/** FastAPI {@code /ai/guardrails/output-check} 응답. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GuardrailCheckResult(
        Boolean isSafe,
        String riskLevel,           // SAFE, WARNING, BLOCKED
        List<Object> detectedIssues,
        String filteredText,        // 마스킹을 마친 결과
        Boolean shouldBlock,
        Boolean shouldRewrite
) {
    public boolean blocked() {
        return Boolean.TRUE.equals(shouldBlock) || "BLOCKED".equals(riskLevel);
    }
}
