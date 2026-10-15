package com.gongsiradar.internal;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

/**
 * 내부 데이터 API({@code /internal/data/**}) 인증. AI 서버만 부른다 — JWT가 아니라 내부 키
 * ({@code X-Internal-API-Key: DATA_API_KEY})로 확인한다.
 * <p>
 * 이 키는 Spring → AI 서버 키(AI_SERVER_API_KEY)와 다른 값이다. 한쪽 키가 새도 반대 방향 호출은 막힌다.
 * 프런트 프록시는 {@code /api}만 넘기므로 브라우저에서는 이 경로에 닿지 않는다.
 * <p>
 * 모든 응답(401 포함)에 {@code X-Data-Origin}(원천 설정값 sample|opendart)을 싣는다 — AI 서버가 이 값으로 리포트의
 * 가상 샘플 표시와 시세 출처를 정한다. 적재 DB를 읽어도 원천 설정값 기준이다.
 * <p>
 * Security 필터 체인보다 먼저 돈다(그 체인에서는 이 경로를 permitAll로 둔다). 요청 ID 필터 다음이라 401에도
 * X-Request-ID가 붙는다.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class InternalKeyFilter extends OncePerRequestFilter {

    public static final String PREFIX = "/internal/";
    public static final String KEY_HEADER = "X-Internal-API-Key";
    public static final String ORIGIN_HEADER = "X-Data-Origin";

    private final byte[] key;
    private final String origin;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public InternalKeyFilter(@Value("${gongsi.data.internal-key}") String key,
                             @Value("${gongsi.data.source:sample}") String origin) {
        this.key = key.getBytes(StandardCharsets.UTF_8);
        this.origin = origin.toLowerCase();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(PREFIX);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        response.setHeader(ORIGIN_HEADER, origin);
        String given = request.getHeader(KEY_HEADER);
        // 길이가 달라도 시간 차이가 나지 않게 비교한다
        if (given == null || !MessageDigest.isEqual(key, given.getBytes(StandardCharsets.UTF_8))) {
            log.warn("내부 데이터 API 키 불일치: {} {}", request.getMethod(), request.getRequestURI());
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            objectMapper.writeValue(response.getOutputStream(), Map.of("detail", "invalid internal API key"));
            return;
        }
        String user = request.getHeader("X-User-Id");
        log.info("internal data {} {}{} user={}", request.getMethod(), request.getRequestURI(),
                request.getQueryString() == null ? "" : "?" + request.getQueryString(), user == null ? "-" : user);
        chain.doFilter(request, response);
    }
}
