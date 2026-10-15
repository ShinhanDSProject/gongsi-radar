package com.gongsiradar.auth.dto;

import jakarta.validation.constraints.NotBlank;

public record LoginRequest(
        @NotBlank String userId,
        @NotBlank String password
) {}
