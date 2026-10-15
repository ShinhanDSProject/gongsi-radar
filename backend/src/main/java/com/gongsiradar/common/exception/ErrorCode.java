package com.gongsiradar.common.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ErrorCode {
    UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED"),
    FORBIDDEN(HttpStatus.FORBIDDEN, "FORBIDDEN"),
    NOT_FOUND(HttpStatus.NOT_FOUND, "NOT_FOUND"),
    VALIDATION_ERROR(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR"),
    GUARDRAIL_BLOCKED(HttpStatus.UNPROCESSABLE_ENTITY, "GUARDRAIL_BLOCKED"),
    KILL_SWITCH_ACTIVE(HttpStatus.SERVICE_UNAVAILABLE, "KILL_SWITCH_ACTIVE"),
    LLM_PROVIDER_ERROR(HttpStatus.BAD_GATEWAY, "LLM_PROVIDER_ERROR"),
    RATE_LIMIT_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "RATE_LIMIT_EXCEEDED"),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR"),
    AI_SERVER_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "AI_SERVER_UNAVAILABLE"),
    CORE_PUBLICATION_REJECTED(HttpStatus.CONFLICT, "CORE_PUBLICATION_REJECTED"),   // Core Zone 발행 원장이 거절
    CORE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "CORE_UNAVAILABLE"),
    REPORT_LOCKED(HttpStatus.CONFLICT, "REPORT_LOCKED"),                           // 발행 요청 이후 수정 불가
    SELF_APPROVAL_FORBIDDEN(HttpStatus.FORBIDDEN, "SELF_APPROVAL_FORBIDDEN");      // 자기 요청 승인 불가

    private final HttpStatus status;
    private final String code;
}
