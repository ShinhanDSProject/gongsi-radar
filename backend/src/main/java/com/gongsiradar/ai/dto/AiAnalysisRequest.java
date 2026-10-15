package com.gongsiradar.ai.dto;

import java.util.List;
import java.util.Map;

/** FastAPI {@code POST /ai/analyses} 본문. CONTRACT §4. */
public record AiAnalysisRequest(
        Long requestId,
        String userId,
        String company,
        Integer bsnsYear,
        String reprtCode,
        String query,
        List<String> scope,
        Map<String, Object> options
) {}
