package com.gongsiradar.glossary.dto;

import jakarta.validation.constraints.Size;

/** 승인이면 comment(선택), 반려면 comment(필수 — 무엇을 고쳐야 하는지). */
public record GlossaryDecisionRequest(@Size(max = 500) String comment) {}
