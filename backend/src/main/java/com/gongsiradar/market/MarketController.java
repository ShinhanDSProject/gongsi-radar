package com.gongsiradar.market;

import com.gongsiradar.ai.AiClient;
import com.gongsiradar.common.ApiException;
import com.gongsiradar.common.ApiResponse;
import com.gongsiradar.common.CurrentUser;
import com.gongsiradar.common.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Locale;
import java.util.Set;

/**
 * 시장 화면(CONTRACT §9) — 지수 추이·시가총액 추이·업종 지도·최근 정기보고서. FastAPI 데이터 프록시.
 * <p>
 * 시세 데이터라 MARKET_DATA_READ가 필요하다. 같은 Scope를 X-User-Scopes로 넘겨 Tool Gateway가 다시 판단하고
 * 호출 기록(agent_tool_call_log)에 남긴다. 시장 필터 값은 여기서 먼저 걸러 잘못된 값이 AI 서버까지 가지 않게 한다.
 */
@RestController
@RequestMapping("/api/market")
@RequiredArgsConstructor
public class MarketController {

    private static final Set<String> MARKETS = Set.of("ALL", "KOSPI", "KOSDAQ", "KONEX");

    private final AiClient aiClient;

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_MARKET_DATA_READ')")
    public ApiResponse<Object> overview(
            @AuthenticationPrincipal String userId,
            @RequestParam(defaultValue = "ALL") String market) {
        String m = market.toUpperCase(Locale.ROOT);
        if (!MARKETS.contains(m)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "market은 ALL·KOSPI·KOSDAQ·KONEX 중 하나입니다.");
        }
        return ApiResponse.success(aiClient.market(m, userId, CurrentUser.scopes()));
    }
}
