package com.gongsiradar.admin.dto;

import com.gongsiradar.admin.KillSwitchStatus;

import java.time.LocalDateTime;

public record KillSwitchDto(
        boolean killSwitchActive,
        String reason,
        String toggledBy,
        LocalDateTime since
) {
    public static KillSwitchDto from(KillSwitchStatus e) {
        return new KillSwitchDto(Boolean.TRUE.equals(e.getActive()), e.getReason(),
                e.getToggledBy(), e.getToggledAt());
    }

    /** 기록이 하나도 없으면 꺼진 것으로 본다. FastAPI도 같은 규칙을 쓴다. */
    public static KillSwitchDto off() {
        return new KillSwitchDto(false, null, null, null);
    }
}
