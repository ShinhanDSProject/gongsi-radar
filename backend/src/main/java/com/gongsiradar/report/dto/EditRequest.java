package com.gongsiradar.report.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 검토자 문구 수정. {@code itemId}는 changes[].id 또는 relations[].account_key다.
 */
public record EditRequest(
        @NotBlank @Size(max = 128) String itemId,
        @NotBlank @Size(max = 2000) String value
) {}
