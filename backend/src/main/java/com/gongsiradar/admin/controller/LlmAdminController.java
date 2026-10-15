package com.gongsiradar.admin.controller;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.response.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * LLM Provider 조회·전환.
 * <p>
 * 전환 자체는 AI 서버가 하지만, "누가 바꿀 수 있는가"는 여기서 가린다.
 * AI 서버는 사람을 모른다 — 내부 키를 가진 호출자(Spring)만 믿고,
 * Senior 권한 검증과 감사 기록은 Service Layer의 몫이다. Kill Switch와 같은 구도.
 */
@RestController
@RequestMapping("/api/admin/llm")
@RequiredArgsConstructor
public class LlmAdminController {

    private final AiClient aiClient;
    private final AuditService auditService;

    @GetMapping("/providers")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<Map<String, Object>> providers(@AuthenticationPrincipal String userId) {
        return ApiResponse.success(aiClient.llmProviders(userId));
    }

    @PostMapping("/switch")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<Map<String, Object>> switchProvider(
            @AuthenticationPrincipal String userId,
            @Valid @RequestBody SwitchLlmRequest req) {
        Map<String, Object> result = aiClient.switchLlmProvider(req.provider(), userId);
        // 사람의 결정은 Spring이 남긴다. AI 서버 쪽에는 실행 로그가 따로 남는다
        auditService.record("LLM_PROVIDER_SWITCHED", userId,
                Map.of("provider", req.provider()));
        return ApiResponse.success(result);
    }

    public record SwitchLlmRequest(@NotBlank String provider) {}
}
