package com.gongsiradar.glossary.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.util.List;

/** 용어 작성·수정. 별칭·관련 용어는 목록으로 받아 쉼표로 저장한다. */
public record GlossaryTermRequest(
        @NotBlank @Size(max = 100) String term,
        List<@Size(max = 100) String> aliases,
        @NotBlank @Size(max = 2000) String definition,
        @Size(max = 500) String usageNote,
        List<@Size(max = 100) String> related,
        @Size(max = 300) String source
) {}
