package com.gongsiradar.ai.dto;

/** AI 서버 {@code POST /ai/glossary/draft} 응답. mock이면 정의를 지어내지 않았다는 뜻이다. */
public record GlossaryDraft(String definition, String usageNote, boolean mock, String model) {
}
