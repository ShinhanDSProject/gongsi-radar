package com.gongsiradar.report;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.gongsiradar.common.ApiException;
import com.gongsiradar.common.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

/**
 * RadarReport JSON(body_json)을 읽고 고치는 곳을 한 군데로 모은다.
 * <p>
 * 필드 이름은 {@code ai-server/radar/schemas.py}(snake_case)를 따른다 —
 * {@code changes[].id/summary}, {@code relations[].account_key/statement},
 * {@code review.{status, reviewer, decided_at, comment, events[]}},
 * {@code review.events[] = {at, actor, action, item_id, detail}}.
 */
@Component
@RequiredArgsConstructor
public class ReportBody {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private final ObjectMapper objectMapper;

    /** 고친 항목의 종류. 감사 로그와 review 이벤트에 남긴다. */
    public enum EditedField { CHANGE_SUMMARY, RELATION_STATEMENT }

    /** 수정 결과. {@code previous}는 바꾸기 전 문구 — review 이벤트의 detail에 남겨 AI 초안을 잃지 않는다. */
    public record Edit(EditedField field, String previous) {}

    public ObjectNode parse(String bodyJson) {
        try {
            JsonNode node = objectMapper.readTree(bodyJson);
            if (node instanceof ObjectNode o) {
                return o;
            }
        } catch (Exception ignored) {
            // 아래에서 처리
        }
        throw new ApiException(ErrorCode.INTERNAL_ERROR, "리포트 본문(JSON)을 읽을 수 없음");
    }

    public String write(JsonNode body) {
        try {
            return objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "리포트 본문 직렬화 실패");
        }
    }

    /** 목록·상세 응답용. 깨진 본문이어도 화면 전체를 실패시키지 않는다. */
    public JsonNode parseLenient(String bodyJson) {
        try {
            return objectMapper.readTree(bodyJson);
        } catch (Exception e) {
            return JsonNodeFactory.instance.nullNode();
        }
    }

    /**
     * 항목 하나의 문구를 바꾼다. changes[].id가 먼저, 없으면 relations[].account_key를 찾는다.
     * 스키마에 없는 필드는 만들지 않는다 — 정본은 schemas.py다.
     */
    public Edit applyEdit(ObjectNode body, String itemId, String value) {
        JsonNode changes = body.path("changes");
        if (changes.isArray()) {
            for (JsonNode c : changes) {
                if (c instanceof ObjectNode o && itemId.equals(o.path("id").asText(null))) {
                    String previous = o.path("summary").asText("");
                    o.put("summary", value);
                    return new Edit(EditedField.CHANGE_SUMMARY, previous);
                }
            }
        }
        JsonNode relations = body.path("relations");
        if (relations.isArray()) {
            for (JsonNode r : relations) {
                if (r instanceof ObjectNode o && itemId.equals(o.path("account_key").asText(null))) {
                    String previous = o.path("statement").asText("");
                    o.put("statement", value);
                    return new Edit(EditedField.RELATION_STATEMENT, previous);
                }
            }
        }
        throw new ApiException(ErrorCode.NOT_FOUND, "리포트에서 항목을 찾지 못했다: " + itemId);
    }

    /** review 블록을 꺼낸다. 없으면 "검토 대기"로 만든다. */
    public ObjectNode review(ObjectNode body) {
        JsonNode review = body.path("review");
        ObjectNode r;
        if (review instanceof ObjectNode o) {
            r = o;
        } else {
            r = body.putObject("review");
            r.put("status", "검토 대기");
        }
        if (!r.path("events").isArray()) {
            r.putArray("events");
        }
        return r;
    }

    public void appendEvent(ObjectNode body, String actor, String action, String itemId, String detail) {
        ArrayNode events = (ArrayNode) review(body).get("events");
        ObjectNode e = events.addObject();
        e.put("at", now());
        e.put("actor", actor);
        e.put("action", action);
        if (itemId == null) {
            e.putNull("item_id");
        } else {
            e.put("item_id", itemId);
        }
        e.put("detail", detail == null ? "" : detail);
    }

    /** 결재 결과를 review 블록에 반영한다. status: "승인됨" | "수정 요청". */
    public void decide(ObjectNode body, String status, String reviewer, String comment) {
        ObjectNode r = review(body);
        r.put("status", status);
        r.put("reviewer", reviewer);
        r.put("decided_at", now());
        if (comment == null) {
            r.putNull("comment");
        } else {
            r.put("comment", comment);
        }
    }

    // ── 리포트 래퍼 필드(CONTRACT §6.1) ──

    public static String text(JsonNode node, String field) {
        JsonNode v = node.path(field);
        return v.isTextual() && !v.asText().isBlank() ? v.asText() : null;
    }

    public static String now() {
        return OffsetDateTime.now(SEOUL).truncatedTo(ChronoUnit.SECONDS)
                .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }
}
