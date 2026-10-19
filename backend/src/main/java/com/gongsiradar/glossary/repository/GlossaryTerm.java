package com.gongsiradar.glossary.repository;

import com.gongsiradar.common.repository.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 용어집 한 항목(#14). 화면 툴팁의 정본이라 사람이 검토·승인한 것만 게시한다.
 * <p>
 * 상태: DRAFT(작성 중) → PENDING(검토 대기) → PUBLISHED(게시) / REJECTED(반려). 삭제하지 않고 게시 취소(DRAFT)만 한다.
 * 정의 초안을 LLM이 썼으면 {@code aiDrafted}로 남긴다 — 게시 전 사람이 반드시 읽어야 한다.
 */
@Entity
@Table(name = "glossary_term")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class GlossaryTerm extends BaseEntity {

    public static final String DRAFT = "DRAFT";
    public static final String PENDING = "PENDING";
    public static final String PUBLISHED = "PUBLISHED";
    public static final String REJECTED = "REJECTED";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String term;

    @Column(length = 500)
    private String aliases;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String definition;

    @Column(name = "usage_note", length = 500)
    private String usageNote;

    @Column(length = 300)
    private String related;

    @Column(length = 300)
    private String source;

    @Column(nullable = false, length = 16)
    private String status;

    @Column(name = "ai_drafted", nullable = false)
    private boolean aiDrafted;

    @Column(name = "created_by", nullable = false, length = 64)
    private String createdBy;

    @Column(name = "submitted_by", length = 64)
    private String submittedBy;

    @Column(name = "reviewed_by", length = 64)
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(name = "review_comment", length = 500)
    private String reviewComment;

    public boolean editable() {
        return DRAFT.equals(status) || REJECTED.equals(status);
    }

    public void edit(String term, String aliases, String definition, String usageNote, String related, String source,
                     boolean aiDrafted) {
        this.term = term;
        this.aliases = aliases;
        this.definition = definition;
        this.usageNote = usageNote;
        this.related = related;
        this.source = source;
        this.aiDrafted = aiDrafted;
    }

    public void submit(String userId) {
        this.status = PENDING;
        this.submittedBy = userId;
        this.reviewedBy = null;
        this.reviewedAt = null;
        this.reviewComment = null;
    }

    public void decide(String status, String reviewer, String comment) {
        this.status = status;
        this.reviewedBy = reviewer;
        this.reviewedAt = LocalDateTime.now();
        this.reviewComment = comment;
    }

    public void unpublish() {
        this.status = DRAFT;
    }
}
