package com.gongsiradar.common.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * 요청마다 상관관계 ID를 만들어 심는다.
 * <p>
 * 헤더로 들어온 {@code X-Request-ID}가 있으면 그대로 쓴다. 앞단(Vite 프록시·게이트웨이)이
 * 이미 ID를 붙여 보냈다면 여기서 새로 만들면 추적이 끊긴다.
 * <p>
 * 응답에도 실어 준다. 사용자가 오류를 문의할 때 이 값 하나면 세 시스템의 기록을 다 찾을 수 있다.
 * <p>
 * 같은 값을 {@link MDC}에도 넣는다. {@code application.yaml}의 로그 패턴에 {@code %X{requestUid}}를
 * 걸어 뒀으므로, 이 요청 동안 찍히는 모든 로그 줄에 자동으로 붙는다.
 * <p>
 * Security 필터 체인보다 먼저 돈다({@code HIGHEST_PRECEDENCE}). 그래야 401·403 응답에도 헤더가 붙는다.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestUidFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-ID";
    public static final String MDC_KEY = "requestUid";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String uid = request.getHeader(HEADER);
        // 외부에서 온 값은 길이를 제한한다. DB 컬럼(request_uid)이 VARCHAR(64)다
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            uid = "req-" + UUID.randomUUID();
        }
        RequestContext.set(uid);
        MDC.put(MDC_KEY, uid);
        response.setHeader(HEADER, uid);
        try {
            chain.doFilter(request, response);
        } finally {
            // [주의] 스레드 풀은 재사용된다. 지우지 않으면 다음 요청이 앞 요청의 ID를 물려받는다.
            //        MDC도 ThreadLocal 기반이라 똑같이 지워 줘야 한다
            RequestContext.clear();
            MDC.remove(MDC_KEY);
        }
    }
}
