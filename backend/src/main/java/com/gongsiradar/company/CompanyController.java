package com.gongsiradar.company;

import com.gongsiradar.ai.AiClient;
import com.gongsiradar.common.ApiResponse;
import com.gongsiradar.common.CurrentUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * 기업 목록·상세. FastAPI 데이터 프록시(CONTRACT §3.5).
 * <p>
 * 데이터는 AI 서버의 Tool Gateway(search_companies·get_company_profile)를 거쳐 나온다.
 * Spring은 JWT의 Scope를 {@code X-User-Scopes}로 넘기기만 하고, 시장 지표를 가릴지는
 * Tool Gateway가 같은 Scope로 다시 판단한다(MARKET_DATA_READ가 없으면 valuation: null + 사유).
 * 권한 검사가 Tool 호출 기록과 같은 길에 남게 하기 위해서다.
 */
@RestController
@RequestMapping("/api/companies")
@RequiredArgsConstructor
public class CompanyController {

    private final AiClient aiClient;

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_DISCLOSURE_READ')")
    public ApiResponse<Object> list(
            @AuthenticationPrincipal String userId,
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(aiClient.companies(q, Math.min(Math.max(limit, 1), 500),
                userId, CurrentUser.scopes()));
    }

    @GetMapping("/{corpCode}")
    @PreAuthorize("hasAuthority('SCOPE_DISCLOSURE_READ')")
    public ApiResponse<Object> profile(
            @AuthenticationPrincipal String userId,
            @PathVariable String corpCode) {
        return ApiResponse.success(aiClient.companyProfile(corpCode, userId, CurrentUser.scopes()));
    }
}
