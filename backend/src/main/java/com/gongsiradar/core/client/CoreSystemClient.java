package com.gongsiradar.core.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.common.web.RequestContext;
import com.gongsiradar.common.web.RequestUidFilter;
import com.gongsiradar.core.dto.CorePublicationDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.util.retry.Retry;

import java.time.Duration;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Core Zone 발행 원장에 시스템 권한으로 쓰는 클라이언트. 사람이 결재한 뒤에만 불린다.
 * <p>
 * 접수·승인·반려 세 가지뿐이다. 사용자 요청을 그대로 흘려보내는 통로가 아니라,
 * 결재 결과를 원장에 반영하는 좁은 창구여야 한다. AI 서버는 이 키를 갖지 않는다.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class CoreSystemClient {

    private final WebClient coreWebClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public CorePublicationDto submitPublication(Long reportId, String corpCode, String corpName,
                                                String periodLabel, String title, String contentHash,
                                                String submittedBy, String supersedesId,
                                                String idempotencyKey) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("reportId", reportId);
        body.put("corpCode", corpCode);
        body.put("corpName", corpName);
        body.put("periodLabel", periodLabel);
        body.put("title", title);
        body.put("contentHash", contentHash);
        body.put("submittedBy", submittedBy);
        body.put("supersedesId", supersedesId);

        // 같은 멱등성 키로 재시도하므로, 앞선 시도가 실제로 접수됐더라도 Core가 기존 건을 돌려준다(중복 접수 없음)
        return call(coreWebClient.post()
                .uri("/core/publications")
                .header("X-Idempotency-Key", idempotencyKey)
                .header("X-User-Id", submittedBy)
                .bodyValue(body));
    }

    public CorePublicationDto approvePublication(String publicationId, String decidedBy, String contentHash) {
        return call(coreWebClient.post()
                .uri("/core/publications/{id}/approve", publicationId)
                .header("X-User-Id", decidedBy)
                .bodyValue(Map.of("decidedBy", decidedBy, "contentHash", contentHash)));
    }

    public CorePublicationDto rejectPublication(String publicationId, String decidedBy, String reason) {
        return call(coreWebClient.post()
                .uri("/core/publications/{id}/reject", publicationId)
                .header("X-User-Id", decidedBy)
                .bodyValue(Map.of("decidedBy", decidedBy, "reason", reason == null ? "" : reason)));
    }

    private CorePublicationDto call(WebClient.RequestHeadersSpec<?> spec) {
        try {
            // 결재 쓰기도 같은 상관관계 ID를 달고 나간다.
            // core_log가 이 값을 받아, 조회 경로(AI)와 쓰기 경로(Spring)의 기록이 같은 요청으로 묶인다
            String uid = RequestContext.get();
            if (uid != null && !uid.isBlank()) {
                spec = spec.header(RequestUidFilter.HEADER, uid);
            }
            return spec.retrieve()
                    .bodyToMono(CorePublicationDto.class)
                    // Core는 일부러 503을 내기도 한다(CORE_FAIL_RATE). 두 번까지는 다시 시도한다
                    .retryWhen(Retry.backoff(2, Duration.ofMillis(500))
                            .filter(this::isRetryable))
                    .block();
        } catch (WebClientResponseException.Conflict e) {
            // 중복 발행·대기 중 건 존재·일일 한도·상태 전이 위반·내용 변경. 사용자에게 이유를 그대로 보여 준다
            throw new ApiException(ErrorCode.CORE_PUBLICATION_REJECTED,
                    "Core Zone이 발행을 거절했다", parseError(e));
        } catch (WebClientResponseException.Forbidden | WebClientResponseException.Unauthorized e) {
            // 여기가 뜨면 시스템 키 설정이 틀린 것이다
            log.error("Core Zone 인증 실패. X-System-Key를 확인해야 한다");
            throw new ApiException(ErrorCode.CORE_UNAVAILABLE, "Core Zone 인증 실패");
        } catch (WebClientResponseException.NotFound e) {
            throw new ApiException(ErrorCode.NOT_FOUND, "발행 건을 찾지 못했다");
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            log.error("Core Zone 호출 실패: {}", e.getMessage());
            throw new ApiException(ErrorCode.CORE_UNAVAILABLE, "Core Zone 응답 없음");
        }
    }

    private boolean isRetryable(Throwable t) {
        if (t instanceof WebClientResponseException.ServiceUnavailable) {
            log.warn("Core Zone 503. 다시 시도한다");
            return true;
        }
        return t instanceof WebClientRequestException;
    }

    /** Core 오류 본문의 detail을 꺼낸다. 문자열이면 {error: 문자열}로 감싸 프런트가 같은 모양으로 읽게 한다. */
    Object parseError(WebClientResponseException e) {
        try {
            JsonNode node = objectMapper.readTree(e.getResponseBodyAsString());
            JsonNode detail = node.has("detail") ? node.get("detail") : node;
            if (detail.isTextual()) {
                Map<String, Object> m = new HashMap<>();
                m.put("error", detail.asText());
                return m;
            }
            return objectMapper.convertValue(detail, Object.class);
        } catch (Exception ignored) {
            return e.getResponseBodyAsString();
        }
    }
}
