package com.gongsiradar.analysis.dto;

import com.gongsiradar.analysis.AnalysisRequestStatus;

public record ExecuteResponse(Long requestId, String jobId, AnalysisRequestStatus status) {}
