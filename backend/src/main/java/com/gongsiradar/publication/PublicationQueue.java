package com.gongsiradar.publication;

import com.gongsiradar.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 발행 결재 큐. Core Zone 원장을 그대로 복제하는 것이 아니라, 결재라는 사내 절차를 남기는 곳이다.
 * <p>
 * 발행 사실은 Core Zone이 원본을 갖고, 누가 언제 무슨 의견으로 승인했는지는 여기가 갖는다.
 * <p>
 * 멱등성 키는 Core 호출 <b>전에</b> 이 테이블에 먼저 저장한다(status=SUBMITTING).
 * 응답을 못 받고 끊겨도 같은 키로 다시 보낼 수 있어야 원장에 같은 건이 두 번 생기지 않는다.
 */
@Entity
@Table(name = "publication_queue")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class PublicationQueue extends BaseEntity {

    public static final String SUBMITTING = "SUBMITTING";
    public static final String PENDING = "PENDING";
    public static final String PUBLISHED = "PUBLISHED";
    public static final String REJECTED = "REJECTED";
    public static final String EXPIRED = "EXPIRED";
    public static final String FAILED = "FAILED";
    public static final String SUPERSEDED = "SUPERSEDED";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** Core Zone이 준 ID. 접수 성공 후 채운다. */
    @Column(name = "publication_id", unique = true, length = 64)
    private String publicationId;

    @Column(name = "report_id", nullable = false)
    private Long reportId;

    @Column(name = "idempotency_key", nullable = false, unique = true, length = 64)
    private String idempotencyKey;

    @Column(name = "corp_code", nullable = false, length = 16)
    private String corpCode;

    @Column(name = "corp_name", nullable = false, length = 100)
    private String corpName;

    @Column(name = "period_label", nullable = false, length = 64)
    private String periodLabel;

    @Column(nullable = false, length = 500)
    private String title;

    @Column(name = "content_hash", nullable = false, length = 64)
    private String contentHash;

    private Integer version;

    @Column(name = "supersedes_id", length = 64)
    private String supersedesId;

    @Column(name = "submitted_by", nullable = false, length = 64)
    private String submittedBy;

    @Column(nullable = false, length = 16)
    private String status;

    @Column(name = "decided_by", length = 64)
    private String decidedBy;

    @Column(name = "decided_at")
    private LocalDateTime decidedAt;

    @Column(columnDefinition = "TEXT")
    private String comment;

    @Column(name = "decision_required_by")
    private LocalDateTime decisionRequiredBy;

    /** Core Zone이 접수했다. 원장의 ID·버전·결재 기한을 받아 둔다. */
    public void accepted(String publicationId, String status, Integer version, LocalDateTime decisionRequiredBy) {
        this.publicationId = publicationId;
        this.status = status;
        this.version = version;
        this.decisionRequiredBy = decisionRequiredBy;
    }

    /** Core Zone이 접수를 거절했다. 키는 남겨 둔다 — 무엇을 왜 거절당했는지가 기록이다. */
    public void submitFailed(String reason) {
        this.status = FAILED;
        this.comment = reason;
    }

    /** Core Zone의 결정을 사내 기록에 반영한다. */
    public void applyDecision(String status, String decidedBy, LocalDateTime decidedAt, String comment) {
        this.status = status;
        this.decidedBy = decidedBy;
        this.decidedAt = decidedAt == null ? LocalDateTime.now() : decidedAt;
        this.comment = comment;
    }

    public void applyVersion(Integer version) {
        if (version != null) {
            this.version = version;
        }
    }

    public void markStatus(String status) {
        this.status = status;
    }
}
