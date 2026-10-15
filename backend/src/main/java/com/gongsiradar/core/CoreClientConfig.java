package com.gongsiradar.core;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

/**
 * Core Zone(리포트 발행 원장) 호출용 WebClient. AiClientConfig와 같은 모양이지만 키가 다르다.
 * <p>
 * [보안] 시스템 키는 이 서버에만 있다. AI 서버에는 조회 키만 준다.
 * 두 키를 한 프로세스에 두면 분리한 의미가 없다.
 */
@Configuration
public class CoreClientConfig {

    @Bean
    public WebClient coreWebClient(
            @Value("${gongsi.core.base-url}") String baseUrl,
            @Value("${gongsi.core.system-key}") String systemKey,
            @Value("${gongsi.core.timeout-seconds}") long timeoutSeconds) {

        HttpClient http = HttpClient.create()
                .responseTimeout(Duration.ofSeconds(timeoutSeconds));

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(http))
                .defaultHeader(HttpHeaders.CONTENT_TYPE, "application/json")
                .defaultHeader("X-System-Key", systemKey)
                .defaultHeader("X-Caller", "spring-boot")   // Core 감사 로그(core_log)에 남는다
                .build();
    }
}
