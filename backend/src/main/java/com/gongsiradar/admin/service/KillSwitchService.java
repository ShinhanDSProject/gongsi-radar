package com.gongsiradar.admin.service;

import com.gongsiradar.admin.repository.KillSwitchStatus;
import com.gongsiradar.admin.repository.KillSwitchRepository;

import com.gongsiradar.admin.dto.KillSwitchDto;
import com.gongsiradar.audit.service.AuditService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class KillSwitchService {

    private final KillSwitchRepository repository;
    private final AuditService auditService;

    @Transactional(readOnly = true)
    public KillSwitchDto current() {
        return repository.findFirstByOrderByIdDesc()
                .map(KillSwitchDto::from)
                .orElseGet(KillSwitchDto::off);
    }

    /**
     * 토글. 상태를 고치지 않고 한 줄 더 쌓는다.
     * <p>
     * AI 서버에는 알리지 않는다. FastAPI가 같은 테이블을 스스로 읽어 가기 때문이다.
     * 알림을 보내는 구조로 만들면 그 알림이 유실됐을 때 한쪽만 꺼진 채로 남는다.
     * 대신 FastAPI 쪽 캐시 때문에 최대 몇 초의 지연이 있다.
     */
    @Transactional
    public KillSwitchDto toggle(String userId, boolean enabled, String reason) {
        KillSwitchStatus saved = repository.save(KillSwitchStatus.builder()
                .active(enabled)
                .reason(reason)
                .toggledBy(userId)
                .build());

        Map<String, Object> payload = new HashMap<>();
        payload.put("enabled", enabled);
        payload.put("reason", reason);
        auditService.record("KILL_SWITCH_TOGGLED", userId, payload);

        log.warn("Kill Switch {} by {} ({})", enabled ? "ON" : "OFF", userId, reason);
        return KillSwitchDto.from(saved);
    }
}
