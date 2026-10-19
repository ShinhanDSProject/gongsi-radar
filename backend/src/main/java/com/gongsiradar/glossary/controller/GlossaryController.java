package com.gongsiradar.glossary.controller;

import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.common.web.CurrentUser;
import com.gongsiradar.glossary.dto.GlossaryDecisionRequest;
import com.gongsiradar.glossary.dto.GlossaryTermDto;
import com.gongsiradar.glossary.dto.GlossaryTermRequest;
import com.gongsiradar.glossary.service.GlossaryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 용어집(#14). 게시된 용어는 로그인한 누구나 읽고(화면 툴팁), 초안 작성·검토 요청은 누구나,
 * 승인·반려·게시 취소는 결재자만 한다.
 */
@RestController
@RequestMapping("/api/glossary")
@RequiredArgsConstructor
public class GlossaryController {

    private final GlossaryService service;

    /** 게시된 용어 전체. 화면이 한 번 받아 캐시하고 툴팁에 쓴다. */
    @GetMapping
    public ApiResponse<List<GlossaryTermDto>> published() {
        return ApiResponse.success(service.published());
    }

    /** 관리용 목록(모든 상태). */
    @GetMapping("/manage")
    public ApiResponse<List<GlossaryTermDto>> manage(@RequestParam(required = false) String status) {
        return ApiResponse.success(service.all(status));
    }

    @PostMapping
    public ApiResponse<GlossaryTermDto> create(@AuthenticationPrincipal String userId,
                                               @Valid @RequestBody GlossaryTermRequest req) {
        return ApiResponse.success(service.create(userId, req));
    }

    @PutMapping("/{id}")
    public ApiResponse<GlossaryTermDto> update(@AuthenticationPrincipal String userId, @PathVariable Long id,
                                               @Valid @RequestBody GlossaryTermRequest req) {
        return ApiResponse.success(service.update(id, userId, CurrentUser.isSenior(), req));
    }

    /** LLM 정의 초안. 상태는 바뀌지 않고 ai_drafted 표시만 붙는다 — 게시는 검토를 거친다. */
    @PostMapping("/{id}/ai-draft")
    public ApiResponse<GlossaryTermDto> aiDraft(@AuthenticationPrincipal String userId, @PathVariable Long id) {
        return ApiResponse.success(service.aiDraft(id, userId, CurrentUser.isSenior()));
    }

    @PostMapping("/{id}/submit")
    public ApiResponse<GlossaryTermDto> submit(@AuthenticationPrincipal String userId, @PathVariable Long id) {
        return ApiResponse.success(service.submit(id, userId, CurrentUser.isSenior()));
    }

    @PostMapping("/{id}/approve")
    @PreAuthorize("hasAnyRole('SENIOR_MANAGER','ADMIN')")
    public ApiResponse<GlossaryTermDto> approve(@AuthenticationPrincipal String userId, @PathVariable Long id,
                                                @Valid @RequestBody(required = false) GlossaryDecisionRequest req) {
        return ApiResponse.success(service.approve(id, userId, req));
    }

    @PostMapping("/{id}/reject")
    @PreAuthorize("hasAnyRole('SENIOR_MANAGER','ADMIN')")
    public ApiResponse<GlossaryTermDto> reject(@AuthenticationPrincipal String userId, @PathVariable Long id,
                                               @Valid @RequestBody GlossaryDecisionRequest req) {
        return ApiResponse.success(service.reject(id, userId, req));
    }

    @PostMapping("/{id}/unpublish")
    @PreAuthorize("hasAnyRole('SENIOR_MANAGER','ADMIN')")
    public ApiResponse<GlossaryTermDto> unpublish(@AuthenticationPrincipal String userId, @PathVariable Long id) {
        return ApiResponse.success(service.unpublish(id, userId));
    }
}
