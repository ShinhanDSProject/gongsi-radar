package com.gongsiradar.admin.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record KillSwitchRequest(
        @NotNull Boolean enabled,
        @Size(max = 500) String reason
) {
}
