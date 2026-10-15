package com.gongsiradar.ai.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

@Configuration
public class AiClientConfig {

    @Bean
    public WebClient aiWebClient(
            @Value("${gongsi.ai-server.base-url}") String baseUrl,
            @Value("${gongsi.ai-server.api-key}") String apiKey,
            @Value("${gongsi.ai-server.timeout-seconds}") long timeoutSeconds) {

        HttpClient http = HttpClient.create()
                .responseTimeout(Duration.ofSeconds(timeoutSeconds));

        // 완료된 Job의 result.report(RadarReport)는 원문 문단·표 비교를 담아 수 MB가 될 수 있다.
        // WebClient 기본 버퍼(256KB)로는 DataBufferLimitException이 난다
        ExchangeStrategies strategies = ExchangeStrategies.builder()
                .codecs(c -> c.defaultCodecs().maxInMemorySize(32 * 1024 * 1024))
                .build();

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(http))
                .exchangeStrategies(strategies)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, "application/json")
                .defaultHeader("X-Internal-API-Key", apiKey)
                .build();
    }
}
