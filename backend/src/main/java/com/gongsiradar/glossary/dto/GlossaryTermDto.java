package com.gongsiradar.glossary.dto;

import com.gongsiradar.glossary.repository.GlossaryTerm;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;

public record GlossaryTermDto(
        Long id, String term, List<String> aliases, String definition, String usageNote, List<String> related,
        String source, String status, boolean aiDrafted, String createdBy, String submittedBy, String reviewedBy,
        LocalDateTime reviewedAt, String reviewComment, LocalDateTime updatedAt) {

    public static GlossaryTermDto of(GlossaryTerm t) {
        return new GlossaryTermDto(t.getId(), t.getTerm(), split(t.getAliases()), t.getDefinition(), t.getUsageNote(),
                split(t.getRelated()), t.getSource(), t.getStatus(), t.isAiDrafted(), t.getCreatedBy(),
                t.getSubmittedBy(), t.getReviewedBy(), t.getReviewedAt(), t.getReviewComment(), t.getUpdatedAt());
    }

    public static List<String> split(String csv) {
        if (csv == null || csv.isBlank()) return List.of();
        return Arrays.stream(csv.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList();
    }
}
