package com.gongsiradar.admin;

import com.gongsiradar.ai.AiClient;
import com.gongsiradar.common.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 일일 수집(#3) 상태 — 마지막 수집 시각·단계별 결과·오늘 쓴 호출 수와 남은 예산.
 * <p>
 * 조회만 있다. 수집을 화면에서 시작하는 버튼은 두지 않는다 — 수집은 원천 API 키와 적재 테이블 쓰기 권한을 가진
 * 별도 작업(cron)이 하고, 요청을 받는 서버(Spring·AI)는 그 자격 증명을 갖지 않는다.
 */
@RestController
@RequestMapping("/api/admin/ingest")
@RequiredArgsConstructor
public class IngestAdminController {

    private final AiClient aiClient;

    @GetMapping
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<Map<String, Object>> status(@AuthenticationPrincipal String userId) {
        return ApiResponse.success(aiClient.ingestStatus(userId));
    }
}
