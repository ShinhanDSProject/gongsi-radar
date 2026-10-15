package com.gongsiradar.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.common.ApiResponse;
import com.gongsiradar.common.ErrorCode;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Stateless JWT 보안 설정.
 * <p>
 * CORS는 열지 않는다. 브라우저는 Vite 개발 서버(3100)의 {@code /api} 프록시를 거쳐 같은 출처로 들어온다.
 * <p>
 * 401·403도 공통 응답 형식(ApiResponse)으로 내보낸다. 기본값은 빈 본문이라 프런트가 오류 코드를 읽을 수 없다.
 */
@Configuration
@EnableMethodSecurity                  // @PreAuthorize 활성화
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtFilter;
    private final ObjectMapper objectMapper;

    /** 수집 1회 실행 모드(웹 서버 없음)에서는 만들지 않는다. */
    @Bean
    @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(c -> c.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/auth/**").permitAll()
                        .requestMatchers("/error").permitAll()
                        // 내부 데이터 API는 JWT가 아니라 내부 키로 확인한다(InternalKeyFilter가 이 체인보다 먼저 돈다)
                        .requestMatchers("/internal/data/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("SENIOR_MANAGER")
                        .anyRequest().authenticated())
                .exceptionHandling(e -> e
                        .authenticationEntryPoint((req, res, ex) ->
                                writeError(res, ErrorCode.UNAUTHORIZED, "인증이 필요합니다"))
                        .accessDeniedHandler((req, res, ex) ->
                                writeError(res, ErrorCode.FORBIDDEN, "권한이 없습니다")))
                .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    private void writeError(HttpServletResponse res, ErrorCode code, String message) throws IOException {
        res.setStatus(code.getStatus().value());
        res.setContentType(MediaType.APPLICATION_JSON_VALUE);
        res.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(res.getOutputStream(), ApiResponse.failure(code.getCode(), message, null));
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
