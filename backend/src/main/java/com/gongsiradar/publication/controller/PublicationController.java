package com.gongsiradar.publication.controller;

import com.gongsiradar.publication.service.PublicationService;

import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.common.web.CurrentUser;
import com.gongsiradar.publication.dto.DecisionRequest;
import com.gongsiradar.publication.dto.PublicationDto;
import com.gongsiradar.publication.dto.SubmitPublicationRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 리포트 발행 결재 API. 요청은 리포트 소유자(또는 Senior), 승인·반려는 Senior만.
 * <p>
 * AI Agent는 여기 닿지 못한다. Agent에게는 이 서버를 부를 자격 증명 자체가 없고,
 * AI 서버의 Tool 목록에도 발행·승인 Tool은 등록돼 있지 않다.
 */
@RestController
@RequestMapping("/api/publications")
@RequiredArgsConstructor
public class PublicationController {

    private final PublicationService service;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasAuthority('SCOPE_REPORT_READ')")
    public ApiResponse<PublicationDto> submit(
            @AuthenticationPrincipal String userId,
            @Valid @RequestBody SubmitPublicationRequest req) {
        return ApiResponse.success(service.submit(userId, CurrentUser.isSenior(), req.reportId(), req.comment()));
    }

    @GetMapping("/pending")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<List<PublicationDto>> pending() {
        return ApiResponse.success(service.listPending());
    }

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_REPORT_READ')")
    public ApiResponse<List<PublicationDto>> list(
            @RequestParam(required = false) String corpCode,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(service.search(corpCode, status, limit));
    }

    @PostMapping("/{publicationId}/approve")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<PublicationDto> approve(
            @AuthenticationPrincipal String userId,
            @PathVariable String publicationId,
            @Valid @RequestBody(required = false) DecisionRequest req) {
        String comment = req == null ? null : req.comment();
        return ApiResponse.success(service.approve(userId, publicationId, comment));
    }

    @PostMapping("/{publicationId}/reject")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<PublicationDto> reject(
            @AuthenticationPrincipal String userId,
            @PathVariable String publicationId,
            @Valid @RequestBody(required = false) DecisionRequest req) {
        String reason = req == null ? null : req.reason();
        return ApiResponse.success(service.reject(userId, publicationId, reason));
    }
}
