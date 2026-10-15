package com.gongsiradar.analysis;

import com.gongsiradar.ai.dto.AiJobStatus;
import com.gongsiradar.analysis.dto.AnalysisRequestDto;
import com.gongsiradar.analysis.dto.CreateAnalysisRequest;
import com.gongsiradar.analysis.dto.ExecuteResponse;
import com.gongsiradar.common.ApiResponse;
import com.gongsiradar.common.CurrentUser;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/analysis-requests")
@RequiredArgsConstructor
public class AnalysisRequestController {

    private final AnalysisService service;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasAuthority('SCOPE_DISCLOSURE_READ')")
    public ApiResponse<AnalysisRequestDto> create(
            @AuthenticationPrincipal String userId,
            @Valid @RequestBody CreateAnalysisRequest req) {
        return ApiResponse.success(service.create(userId, CurrentUser.scopes(), req));
    }

    @GetMapping
    public ApiResponse<Page<AnalysisRequestDto>> list(
            @AuthenticationPrincipal String userId,
            @RequestParam(required = false) AnalysisRequestStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(service.list(userId, CurrentUser.isSenior(), status,
                PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100))));
    }

    @GetMapping("/{id}")
    public ApiResponse<AnalysisRequestDto> get(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.get(id, userId, CurrentUser.isSenior()));
    }

    @PostMapping("/{id}/execute")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ApiResponse<ExecuteResponse> execute(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.execute(id, userId, CurrentUser.scopes()));
    }

    /** 폴링용. AI Job이 끝났으면 리포트를 저장하고 갱신된 상태를 돌려준다. */
    @GetMapping("/{id}/status")
    public ApiResponse<AnalysisRequestDto> status(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.refreshStatus(id, userId, CurrentUser.isSenior(), CurrentUser.scopes()));
    }

    /** Timeline·진행 단계 화면용 Job 상세(FastAPI JobStatus 프록시). */
    @GetMapping("/{id}/job")
    public ApiResponse<AiJobStatus> job(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.jobDetail(id, userId, CurrentUser.isSenior(), CurrentUser.scopes()));
    }
}
