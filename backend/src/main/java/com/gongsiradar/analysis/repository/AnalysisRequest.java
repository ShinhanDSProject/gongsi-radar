package com.gongsiradar.analysis.repository;

import com.gongsiradar.common.repository.BaseEntity;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 분석 요청. 회사·사업연도·보고서 종류(+선택 관심 질문)로 전년 대비 공시 비교를 맡긴다.
 * <p>
 * {@code company}는 사용자가 입력한 값 그대로다(종목코드·고유번호·회사명).
 * 어느 회사인지는 AI 서버가 확정하고, 완료 시점에 {@code corpCode}·{@code corpName}을 채운다.
 */
@Entity
@Table(name = "analysis_request")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class AnalysisRequest extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, length = 64)
    private String userId;

    @Column(nullable = false, length = 100)
    private String company;

    @Column(name = "corp_code", length = 16)
    private String corpCode;

    @Column(name = "corp_name", length = 100)
    private String corpName;

    @Column(name = "bsns_year", nullable = false)
    private Integer bsnsYear;

    @Column(name = "reprt_code", nullable = false, length = 8)
    private String reprtCode;

    @Column(columnDefinition = "TEXT")
    private String query;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "scope_json", columnDefinition = "LONGTEXT")
    private List<String> scope;

    @Column(name = "demo_fault_injection", nullable = false)
    private boolean demoFaultInjection;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private AnalysisRequestStatus status;

    @Column(name = "job_id", length = 64)
    private String jobId;

    /** 실행을 시작한 요청의 상관관계 ID. AI 서버·Core Zone 기록을 이 값으로 찾는다. */
    @Column(name = "request_uid", length = 64)
    private String requestUid;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "finished_at")
    private LocalDateTime finishedAt;

    public void markRunning(String jobId, String requestUid) {
        this.status = AnalysisRequestStatus.RUNNING;
        this.jobId = jobId;
        if (requestUid != null) {
            this.requestUid = requestUid;
        }
        this.startedAt = LocalDateTime.now();
    }

    public void markCompleted(String corpCode, String corpName) {
        this.status = AnalysisRequestStatus.COMPLETED;
        if (corpCode != null) this.corpCode = corpCode;
        if (corpName != null) this.corpName = corpName;
        this.finishedAt = LocalDateTime.now();
    }

    public void markFailed() {
        this.status = AnalysisRequestStatus.FAILED;
        this.finishedAt = LocalDateTime.now();
    }

    /** 입력 가드레일이 막은 요청. 다시 실행할 수 없다 — 질문을 바꿔 새로 요청해야 한다. */
    public void markBlocked(String requestUid) {
        this.status = AnalysisRequestStatus.BLOCKED;
        if (requestUid != null) {
            this.requestUid = requestUid;
        }
        this.finishedAt = LocalDateTime.now();
    }
}
