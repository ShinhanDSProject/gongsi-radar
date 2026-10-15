package com.gongsiradar.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.gongsiradar.ai.dto.AiAnalysisRequest;
import com.gongsiradar.ai.dto.AiJobStatus;
import com.gongsiradar.ai.dto.GuardrailCheckResult;
import com.gongsiradar.common.ApiException;
import com.gongsiradar.common.ErrorCode;
import com.gongsiradar.common.RequestContext;
import com.gongsiradar.common.RequestUidFilter;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

/**
 * FastAPI AI 서버 호출. 브라우저는 AI 서버를 모른다 — 내부 키는 이 클래스 밖으로 나가지 않는다.
 * <p>
 * 모든 호출에 세 헤더를 단다.
 * <ul>
 *   <li>{@code X-User-Id}: 누가 시켰는가. FastAPI의 Tool 호출 기록·가드레일 이벤트에 남는다</li>
 *   <li>{@code X-User-Scopes}: JWT에 담긴 Scope(쉼표 구분). Tool Gateway가 이 값으로 권한을 다시 검사한다</li>
 *   <li>{@code X-Request-ID}: 상관관계 ID. FastAPI를 거쳐 Core Zone 로그까지 이어진다</li>
 * </ul>
 * FastAPI 오류 본문 {@code {"detail":{"error":"..."}}}을 {@link ErrorCode}로 옮긴다.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class AiClient {

    private final WebClient aiWebClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE =
            new ParameterizedTypeReference<>() {};

    // ───────────────────────── 분석 Job ─────────────────────────

    public AiJobStatus startAnalysis(AiAnalysisRequest req, List<String> userScopes) {
        return call(() -> aiWebClient.post()
                .uri("/ai/analyses")
                .headers(h -> withUser(h, req.userId(), userScopes))
                .bodyValue(req)
                .retrieve()
                .bodyToMono(AiJobStatus.class));
    }

    public AiJobStatus getJob(String jobId, String userId, List<String> userScopes) {
        return call(() -> aiWebClient.get()
                .uri("/ai/jobs/{jobId}", jobId)
                .headers(h -> withUser(h, userId, userScopes))
                .retrieve()
                .bodyToMono(AiJobStatus.class));
    }

    // ───────────────────────── 가드레일 ─────────────────────────

    /** 검토자가 고친 문구를 리포트에 넣기 전에 출력 가드레일로 검사한다. */
    public GuardrailCheckResult outputCheck(String text, String userId, Map<String, Object> context) {
        Map<String, Object> body = new HashMap<>();
        body.put("text", text);
        body.put("userId", userId);
        body.put("context", context);
        return call(() -> aiWebClient.post()
                .uri("/ai/guardrails/output-check")
                .headers(h -> withUser(h, userId, null))
                .bodyValue(body)
                .retrieve()
                .bodyToMono(GuardrailCheckResult.class));
    }

    // ───────────────────────── 데이터 프록시 ─────────────────────────
    // 응답은 가공 없이 흘려보낸다. Spring의 몫은 "누가 무엇을 볼 수 있는가"이지 데이터 모양이 아니다

    public Object companies(String q, Integer limit, String userId, List<String> userScopes) {
        return call(() -> aiWebClient.get()
                .uri(b -> {
                    b.path("/ai/companies");
                    if (q != null && !q.isBlank()) b.queryParam("q", q);
                    if (limit != null) b.queryParam("limit", limit);
                    return b.build();
                })
                .headers(h -> withUser(h, userId, userScopes))
                .retrieve()
                .bodyToMono(Object.class));
    }

    public Object companyProfile(String corpCode, String userId, List<String> userScopes) {
        return call(() -> aiWebClient.get()
                .uri("/ai/companies/{corpCode}", corpCode)
                .headers(h -> withUser(h, userId, userScopes))
                .retrieve()
                .bodyToMono(Object.class));
    }

    public Object agents(String userId, List<String> userScopes) {
        return call(() -> aiWebClient.get()
                .uri("/ai/agents")
                .headers(h -> withUser(h, userId, userScopes))
                .retrieve()
                .bodyToMono(Object.class));
    }

    // ───────────────────────── LLM provider (관리자) ─────────────────────────

    public Map<String, Object> llmProviders(String userId) {
        return call(() -> aiWebClient.get()
                .uri("/ai/llm/providers")
                .headers(h -> withUser(h, userId, null))
                .retrieve()
                .bodyToMono(MAP_TYPE));
    }

    public Map<String, Object> switchLlmProvider(String provider, String userId) {
        try {
            return aiWebClient.post()
                    .uri("/ai/llm/switch")
                    .headers(h -> withUser(h, userId, null))
                    .bodyValue(Map.of("provider", provider))
                    .retrieve()
                    .bodyToMono(MAP_TYPE)
                    .block();
        } catch (WebClientResponseException.Forbidden e) {
            // 폐쇄망 모드에서 외부 provider를 고른 경우. 요청은 올바르지만 정책이 막는다
            throw new ApiException(ErrorCode.FORBIDDEN,
                    "폐쇄망 모드에서는 선택할 수 없는 provider입니다", parseDetail(e));
        } catch (WebClientResponseException.BadRequest e) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,
                    "지원하지 않는 provider입니다", parseDetail(e));
        } catch (WebClientResponseException e) {
            throw translate(e);
        } catch (WebClientRequestException e) {
            throw unavailable(e);
        }
    }

    // ───────────────────────── 공통 ─────────────────────────

    private <T> T call(Supplier<Mono<T>> request) {
        try {
            return request.get().block();
        } catch (WebClientResponseException e) {
            throw translate(e);
        } catch (WebClientRequestException e) {
            // 연결 거부·타임아웃. AI 서버가 떠 있지 않다
            throw unavailable(e);
        }
    }

    private ApiException unavailable(WebClientRequestException e) {
        log.warn("AI server unreachable: {}", e.getMessage());
        return new ApiException(ErrorCode.AI_SERVER_UNAVAILABLE, "AI 서버 응답 없음");
    }

    /**
     * FastAPI 오류를 계약의 ErrorCode로 옮긴다.
     * <p>
     * 우선 {@code detail.error} 값이 ErrorCode 이름과 같으면 그대로 쓴다(GUARDRAIL_BLOCKED·KILL_SWITCH_ACTIVE 등).
     * 없으면 HTTP 상태로 판단한다. 503은 두 가지다 — AI 서버가 죽었거나, Kill Switch가 켜져 있거나.
     */
    ApiException translate(WebClientResponseException e) {
        Object detail = parseDetail(e);
        String errorName = null;
        if (detail instanceof Map<?, ?> m && m.get("error") instanceof String s) {
            errorName = s;
        }
        ErrorCode code = errorName == null ? null : byName(errorName);
        int status = e.getStatusCode().value();

        if (code == null) {
            code = switch (status) {
                case 400 -> ErrorCode.VALIDATION_ERROR;
                case 403 -> ErrorCode.FORBIDDEN;
                case 404 -> ErrorCode.NOT_FOUND;
                // FastAPI 자체 검증 오류(detail이 배열)는 입력 형식 문제, 그 밖의 422는 가드레일 차단
                case 422 -> (detail instanceof List<?>) ? ErrorCode.VALIDATION_ERROR : ErrorCode.GUARDRAIL_BLOCKED;
                case 429 -> ErrorCode.RATE_LIMIT_EXCEEDED;
                case 401, 503 -> ErrorCode.AI_SERVER_UNAVAILABLE;
                default -> ErrorCode.LLM_PROVIDER_ERROR;
            };
        }
        if (status == 401) {
            log.error("AI 서버 인증 실패. X-Internal-API-Key 설정을 확인해야 한다");
        } else if (status >= 500) {
            log.error("AI server error: {} {}", status, e.getResponseBodyAsString());
        } else {
            log.info("AI server {}: {}", status, e.getResponseBodyAsString());
        }
        return new ApiException(code, messageOf(code), detail);
    }

    private static ErrorCode byName(String name) {
        for (ErrorCode c : ErrorCode.values()) {
            if (c.getCode().equals(name)) return c;
        }
        return null;
    }

    private static String messageOf(ErrorCode code) {
        return switch (code) {
            case GUARDRAIL_BLOCKED -> "요청에 사용할 수 없는 내용이 포함되어 있습니다";
            case KILL_SWITCH_ACTIVE -> "AI 서비스가 점검 중입니다";
            case AI_SERVER_UNAVAILABLE -> "AI 서버 응답 없음";
            case NOT_FOUND -> "AI 서버에서 대상을 찾지 못했다";
            case FORBIDDEN -> "권한이 없습니다";
            case VALIDATION_ERROR -> "AI 서버가 요청 형식을 거부했다";
            case RATE_LIMIT_EXCEEDED -> "요청 한도를 넘었습니다";
            default -> "AI 처리 오류";
        };
    }

    /** FastAPI의 {@code {"detail": ...}}에서 detail만 꺼낸다. JSON이 아니면 본문 문자열을 그대로 둔다. */
    private Object parseDetail(WebClientResponseException e) {
        String body = e.getResponseBodyAsString();
        try {
            JsonNode node = objectMapper.readTree(body);
            JsonNode detail = node.has("detail") ? node.get("detail") : node;
            return objectMapper.convertValue(detail, Object.class);
        } catch (Exception ignored) {
            return body == null || body.isBlank() ? null : body;
        }
    }

    /**
     * 사용자·상관관계 헤더를 얹는다. 필터를 타지 않는 경로(테스트·배치)에서는 값이 없을 수 있어
     * null이면 그냥 붙이지 않는다 — 이 헤더가 없다고 호출이 실패해서는 안 된다.
     */
    private static void withUser(HttpHeaders headers, String userId, List<String> scopes) {
        if (userId != null && !userId.isBlank()) {
            headers.set("X-User-Id", userId);
        }
        if (scopes != null) {
            headers.set("X-User-Scopes", String.join(",", scopes));
        }
        String uid = RequestContext.get();
        if (uid != null && !uid.isBlank()) {
            headers.set(RequestUidFilter.HEADER, uid);
        }
    }
}
