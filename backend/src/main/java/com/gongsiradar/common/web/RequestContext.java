package com.gongsiradar.common.web;

/**
 * 요청 하나를 관통하는 상관관계 ID.
 * <p>
 * 이 값이 Spring Boot의 {@code audit_log}, FastAPI의 {@code agent_tool_call_log}·
 * {@code guardrail_event}, Core Zone의 {@code core_log}에 모두 같은 값으로 들어간다.
 * 세 기록이 따로 놀면 "이 발행은 누가 어떤 분석을 근거로 요청했는가"에 답할 수 없다.
 * <p>
 * ThreadLocal이라 비동기 실행에는 따라가지 않는다. 요청 처리는 서블릿 스레드
 * 안에서 끝나므로 문제가 없지만, {@code @Async}를 도입하면 명시적으로 넘겨야 한다.
 */
public final class RequestContext {

    private static final ThreadLocal<String> UID = new ThreadLocal<>();

    private RequestContext() {
    }

    public static void set(String uid) {
        UID.set(uid);
    }

    public static String get() {
        return UID.get();
    }

    public static void clear() {
        UID.remove();
    }
}
