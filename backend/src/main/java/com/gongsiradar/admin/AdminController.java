package com.gongsiradar.admin;

import com.gongsiradar.admin.dto.GuardrailEventDto;
import com.gongsiradar.admin.dto.KillSwitchDto;
import com.gongsiradar.admin.dto.KillSwitchRequest;
import com.gongsiradar.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 관리자 API. Kill Switch와 가드레일 이벤트 조회.
 *
 * 비상 정지 버튼이 AI 서버가 아니라 여기 있는 이유가 있다. 오작동한 쪽이 자기를 멈추는
 * 구조는 믿을 수 없다. 멈추는 권한은 멈춰야 할 대상 바깥에 두어야 한다.
 */
@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
public class AdminController {

    private final KillSwitchService killSwitchService;
    private final GuardrailEventRepository guardrailEventRepository;

    @GetMapping("/kill-switch")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<KillSwitchDto> getKillSwitch() {
        return ApiResponse.success(killSwitchService.current());
    }

    @PostMapping("/kill-switch")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<KillSwitchDto> toggleKillSwitch(
            @AuthenticationPrincipal String userId,
            @Valid @RequestBody KillSwitchRequest req) {
        return ApiResponse.success(
                killSwitchService.toggle(userId, req.enabled(), req.reason()));
    }

    @GetMapping("/guardrail-events")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<List<GuardrailEventDto>> guardrailEvents(
            @RequestParam(required = false) String severity,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(
                guardrailEventRepository.search(severity, PageRequest.of(0, Math.min(limit, 200)))
                        .stream().map(GuardrailEventDto::from).toList());
    }
}
