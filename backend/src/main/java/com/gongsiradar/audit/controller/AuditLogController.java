package com.gongsiradar.audit.controller;

import com.gongsiradar.audit.repository.AuditLogRepository;

import com.gongsiradar.audit.dto.AuditLogDto;
import com.gongsiradar.common.response.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 감사 로그 조회. Senior Manager만 볼 수 있다.
 * <p>
 * 쓰기 엔드포인트는 만들지 않는다. 감사 로그를 API로 넣을 수 있으면
 * 누구든 원하는 기록을 만들어 넣을 수 있게 된다.
 */
@RestController
@RequestMapping("/api/audit")
@RequiredArgsConstructor
public class AuditLogController {

    private final AuditLogRepository repository;

    @GetMapping
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<List<AuditLogDto>> list(
            @RequestParam(required = false) String type,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(
                repository.search(type, PageRequest.of(0, Math.min(limit, 200)))
                        .stream().map(AuditLogDto::from).toList());
    }

    /** 요청 하나가 남긴 기록을 모아 본다. 상관관계 ID의 쓸모가 여기서 드러난다. */
    @GetMapping("/trace/{requestUid}")
    @PreAuthorize("hasRole('SENIOR_MANAGER')")
    public ApiResponse<List<AuditLogDto>> trace(@PathVariable String requestUid) {
        return ApiResponse.success(
                repository.findByRequestUidOrderByIdAsc(requestUid)
                        .stream().map(AuditLogDto::from).toList());
    }
}
