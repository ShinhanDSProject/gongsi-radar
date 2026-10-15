package com.gongsiradar.ai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/** FastAPI {@code GET /ai/jobs/{jobId}}의 JobStatus. CONTRACT §4. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record AiJobStatus(
        String jobId,
        String status,        // RUNNING, COMPLETED, FAILED
        Double progress,
        String currentStep,   // PLANNING → DISCLOSURE → FINANCIAL → REVIEW → WRITING → DONE
        Map<String, Object> result,                  // {report: RadarReport} | {error: string} | null
        List<Map<String, Object>> agentExecutions
) {}
