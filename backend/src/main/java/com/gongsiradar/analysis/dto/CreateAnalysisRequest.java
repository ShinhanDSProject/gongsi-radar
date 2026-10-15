package com.gongsiradar.analysis.dto;

import jakarta.validation.constraints.*;

public record CreateAnalysisRequest(
        @NotBlank @Size(max = 100)
        String company,                                  // 종목코드·고유번호·회사명

        @NotNull @Min(2000) @Max(2100)
        Integer bsnsYear,

        @NotBlank @Pattern(regexp = "11011|11012|11013|11014")
        String reprtCode,                                // 사업·반기·1분기·3분기

        @Size(max = 1000)
        String query,                                    // 선택: 관심 질문(입력 가드레일 대상)

        Boolean demoFaultInjection
) {}
