package com.gongsiradar.report;

import com.gongsiradar.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

/**
 * 분석 리포트. AI 서버가 만든 RadarReport JSON을 문자열 그대로 보관한다.
 * <p>
 * 본문을 컬럼으로 쪼개지 않는 이유: 리포트 스키마의 정본은 {@code ai-server/radar/schemas.py}다.
 * Spring이 필드를 하나하나 매핑하면 AI 쪽 스키마가 바뀔 때마다 여기도 같이 깨진다.
 * Spring이 직접 고치는 곳은 검토자 수정(changes[].summary·relations[].statement)과 review 블록뿐이다.
 */
@Entity
@Table(name = "analysis_report")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class AnalysisReport extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, unique = true)
    private Long requestId;

    @Column(nullable = false, length = 500)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String summary;

    @Column(name = "body_json", nullable = false, columnDefinition = "LONGTEXT")
    private String bodyJson;

    @Column(columnDefinition = "TEXT")
    private String disclaimer;

    @Enumerated(EnumType.STRING)
    @Column(name = "approval_status", nullable = false, length = 16)
    private ApprovalStatus approvalStatus;

    @Column(name = "publication_id", length = 64)
    private String publicationId;

    /** 발행 요청 시점 body_json의 SHA-256. Core Zone 원장에 같은 값이 남는다. */
    @Column(name = "content_hash", length = 64)
    private String contentHash;

    public void updateBody(String bodyJson) {
        this.bodyJson = bodyJson;
    }

    public void markPending(String publicationId, String contentHash) {
        this.approvalStatus = ApprovalStatus.PENDING;
        this.publicationId = publicationId;
        this.contentHash = contentHash;
    }

    public void markApproved(String bodyJson) {
        this.approvalStatus = ApprovalStatus.APPROVED;
        this.bodyJson = bodyJson;
    }

    public void markRejected(String bodyJson) {
        this.approvalStatus = ApprovalStatus.REJECTED;
        this.bodyJson = bodyJson;
    }

    /** 결재 기한이 지나 원장에서 만료된 경우. 다시 수정·재요청할 수 있게 초안으로 되돌린다. */
    public void backToDraft() {
        this.approvalStatus = ApprovalStatus.DRAFT;
    }
}
