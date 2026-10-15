package com.gongsiradar.report;

import com.gongsiradar.common.ApiResponse;
import com.gongsiradar.common.CurrentUser;
import com.gongsiradar.report.dto.EditRequest;
import com.gongsiradar.report.dto.ReportDto;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/reports")
@RequiredArgsConstructor
public class ReportController {

    private final ReportService service;

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_REPORT_READ')")
    public ApiResponse<Page<ReportDto>> list(
            @AuthenticationPrincipal String userId,
            @RequestParam(required = false) ApprovalStatus approvalStatus,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(service.list(userId, CurrentUser.isSenior(), approvalStatus,
                PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100))));
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_REPORT_READ')")
    public ApiResponse<ReportDto> get(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.get(id, userId, CurrentUser.isSenior()));
    }

    /** 검토자 문구 수정. 출력 가드레일 통과분만 반영된다. */
    @PostMapping("/{id}/edits")
    @PreAuthorize("hasAuthority('SCOPE_REPORT_READ')")
    public ApiResponse<ReportDto> edit(
            @AuthenticationPrincipal String userId,
            @PathVariable Long id,
            @Valid @RequestBody EditRequest req) {
        return ApiResponse.success(service.edit(id, userId, CurrentUser.isSenior(), req));
    }
}
