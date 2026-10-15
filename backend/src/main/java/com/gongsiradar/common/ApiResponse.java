package com.gongsiradar.common;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.UUID;

/**
 * 공통 응답 봉투. CONTRACT §2.
 * <p>
 * {@code requestId}는 {@link RequestUidFilter}가 심은 상관관계 ID와 같은 값이다.
 * 사용자가 화면에서 본 ID 하나로 audit_log·guardrail_event·core_log를 모두 찾을 수 있게 하기 위해서다.
 * 필터를 타지 않은 경로(테스트 등)에서만 새 UUID를 만든다.
 * <p>
 * 계약 예시가 {@code "error": null}처럼 null 필드를 그대로 보여 주므로 NON_NULL을 걸지 않는다.
 */
public record ApiResponse<T>(
        boolean success,
        T data,
        ErrorPayload error,
        String requestId,
        OffsetDateTime timestamp
) {
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    public record ErrorPayload(String code, String message, Object details) {}

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(true, data, null, currentRequestId(), OffsetDateTime.now(SEOUL));
    }

    public static <T> ApiResponse<T> failure(String code, String message, Object details) {
        return new ApiResponse<>(false, null, new ErrorPayload(code, message, details),
                currentRequestId(), OffsetDateTime.now(SEOUL));
    }

    private static String currentRequestId() {
        String uid = RequestContext.get();
        return (uid == null || uid.isBlank()) ? "req-" + UUID.randomUUID() : uid;
    }
}
