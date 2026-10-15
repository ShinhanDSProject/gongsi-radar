package com.gongsiradar.market.controller;

import com.gongsiradar.market.service.MarketOverviewService;

import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.common.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 시장 화면(CONTRACT §9) — 지수 추이·시가총액 추이·업종 지도·최근 정기보고서. Spring이 직접 계산한다
 * ({@link MarketOverviewService}, 적재 DB 우선). 시세 데이터라 MARKET_DATA_READ가 필요하다.
 */
@RestController
@RequestMapping("/api/market")
@RequiredArgsConstructor
public class MarketController {

    private static final Set<String> MARKETS = Set.of("ALL", "KOSPI", "KOSDAQ", "KONEX");

    private final MarketOverviewService marketOverviewService;

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_MARKET_DATA_READ')")
    public ApiResponse<Map<String, Object>> overview(@RequestParam(defaultValue = "ALL") String market) {
        String m = market.toUpperCase(Locale.ROOT);
        if (!MARKETS.contains(m)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "market은 ALL·KOSPI·KOSDAQ·KONEX 중 하나입니다.");
        }
        return ApiResponse.success(marketOverviewService.overview(m));
    }
}
