package com.gongsiradar.admin.controller;

import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.ingest.service.IngestStatusService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 일일 수집(#3) 상태 — 마지막 수집 시각·단계별 결과·오늘 쓴 호출 수와 남은 예산. 적재 테이블을 앱 계정으로 읽는다.
 * <p>
 * 조회만 있다. 수집을 화면에서 시작하는 버튼은 두지 않는다 — 수집은 예약 작업(gongsi.ingest.cron)이나
 * 1회 실행 모드({@code --gongsi.ingest.run-once=daily})가 수집 전용 계정으로 하고, 요청을 받는 경로는 그 권한을 쓰지 않는다.
 */
@RestController
@RequestMapping("/api/admin/ingest")
@RequiredArgsConstructor
public class IngestAdminController {

    private final IngestStatusService ingestStatusService;

    @GetMapping
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<Map<String, Object>> status() {
        return ApiResponse.success(ingestStatusService.status());
    }
}
