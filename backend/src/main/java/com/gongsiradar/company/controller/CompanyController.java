package com.gongsiradar.company.controller;

import com.gongsiradar.company.service.CompanyService;

import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.common.web.CurrentUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 기업 목록·상세(CONTRACT §3.5, §6.6). Spring이 직접 계산한다(적재 DB 우선, 없으면 원천) — {@link CompanyService}.
 * <p>
 * 시장 지표(valuation)는 MARKET_DATA_READ가 있을 때만 붙인다. 없으면 {@code valuation: null} + valuationNote.
 * 사업 지표·지배구조만 AI 서버 {@code /ai/insights}에서 받아 붙인다(AI 서버가 멈춰도 나머지는 보인다).
 */
@RestController
@RequestMapping("/api/companies")
@RequiredArgsConstructor
public class CompanyController {

    private final CompanyService companyService;

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_DISCLOSURE_READ')")
    public ApiResponse<List<Map<String, Object>>> list(
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(companyService.search(q == null ? "" : q, Math.min(Math.max(limit, 1), 200)));
    }

    @GetMapping("/{corpCode}")
    @PreAuthorize("hasAuthority('SCOPE_DISCLOSURE_READ')")
    public ApiResponse<Map<String, Object>> profile(
            @AuthenticationPrincipal String userId,
            @PathVariable String corpCode) {
        List<String> scopes = CurrentUser.scopes();
        return ApiResponse.success(companyService.profile(corpCode, scopes.contains("MARKET_DATA_READ"), userId, scopes));
    }
}
