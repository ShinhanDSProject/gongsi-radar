package com.gongsiradar.publication.service;

import com.gongsiradar.publication.repository.PublicationQueue;
import com.gongsiradar.publication.repository.PublicationQueueRepository;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.gongsiradar.analysis.repository.AnalysisRequest;
import com.gongsiradar.analysis.repository.AnalysisRequestRepository;
import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.common.util.Hashing;
import com.gongsiradar.core.client.CoreSystemClient;
import com.gongsiradar.core.dto.CorePublicationDto;
import com.gongsiradar.publication.dto.PublicationDto;
import com.gongsiradar.report.repository.AnalysisReport;
import com.gongsiradar.report.repository.AnalysisReportRepository;
import com.gongsiradar.report.support.ReportBody;
import com.gongsiradar.report.service.ReportService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * HITL 발행 결재. 리포트는 여기서 두 번 사람 손을 탄다 — 발행을 요청할 때 한 번, 승인할 때 한 번.
 * <p>
 * AI Agent는 이 서비스를 부를 수 없다. 호출자는 JWT를 들고 온 사람뿐이고,
 * Core Zone 쓰기 키(X-System-Key)는 AI 서버에 없다.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class PublicationService {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private final CoreSystemClient core;
    private final PublicationQueueRepository queue;
    private final AnalysisReportRepository reportRepository;
    private final AnalysisRequestRepository requestRepository;
    private final ReportBody reportBody;
    private final AuditService auditService;
    private final PlatformTransactionManager transactionManager;

    /**
     * 발행 요청. 트랜잭션을 메서드 전체에 걸지 않는다 —
     * 멱등성 키를 담은 SUBMITTING 행은 Core 호출 <b>전에 커밋</b>돼야 한다.
     * 하나의 트랜잭션으로 묶으면 Core 호출이 실패할 때 키까지 롤백돼 재시도에 쓸 수 없다.
     */
    public PublicationDto submit(String userId, boolean senior, Long reportId, String comment) {
        AnalysisReport report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트를 찾을 수 없음"));
        AnalysisRequest request = requestRepository.findById(report.getRequestId())
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트의 분석 요청이 없음"));
        if (!senior && !request.getUserId().equals(userId)) {
            throw new ApiException(ErrorCode.FORBIDDEN, "리포트 소유자 또는 Senior만 발행을 요청할 수 있습니다");
        }
        if (report.getApprovalStatus().locked()) {
            throw new ApiException(ErrorCode.REPORT_LOCKED, "이미 발행 요청됐거나 승인된 리포트",
                    Map.of("approvalStatus", report.getApprovalStatus().name()));
        }
        if (request.getCorpCode() == null || request.getCorpName() == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "회사가 확정되지 않은 리포트는 발행할 수 없습니다");
        }

        // 저장된 body_json 문자열 그대로의 해시. 결재자가 본 내용과 발행되는 내용이 같다는 증거다
        String contentHash = Hashing.sha256Hex(report.getBodyJson());
        String periodLabel = ReportService.periodLabel(request.getBsnsYear(), request.getReprtCode());

        // 같은 회사·기간에 이미 발행된 건이 있으면 정정 발행이다
        String supersedesId = queue.findFirstByCorpCodeAndPeriodLabelAndStatusOrderByIdDesc(
                        request.getCorpCode(), periodLabel, PublicationQueue.PUBLISHED)
                .map(PublicationQueue::getPublicationId)
                .orElse(null);

        // 멱등성 키는 서버가 만든다. 앞선 시도가 응답 없이 끊겼다면(SUBMITTING) 그 키를 다시 쓴다
        PublicationQueue row = queue.findFirstByReportIdAndContentHashAndStatusOrderByIdDesc(
                        reportId, contentHash, PublicationQueue.SUBMITTING)
                .orElseGet(() -> queue.saveAndFlush(PublicationQueue.builder()
                        .reportId(reportId)
                        .idempotencyKey(UUID.randomUUID().toString())
                        .corpCode(request.getCorpCode())
                        .corpName(request.getCorpName())
                        .periodLabel(periodLabel)
                        .title(report.getTitle())
                        .contentHash(contentHash)
                        .supersedesId(supersedesId)
                        .submittedBy(userId)
                        .status(PublicationQueue.SUBMITTING)
                        .comment(comment)
                        .build()));

        CorePublicationDto pub;
        try {
            pub = core.submitPublication(reportId, row.getCorpCode(), row.getCorpName(),
                    row.getPeriodLabel(), row.getTitle(), row.getContentHash(),
                    row.getSubmittedBy(), row.getSupersedesId(), row.getIdempotencyKey());
        } catch (ApiException e) {
            if (e.getErrorCode() == ErrorCode.CORE_PUBLICATION_REJECTED) {
                // 확정 거절. 행을 FAILED로 닫는다. 응답 없음(CORE_UNAVAILABLE)은 결과를 모르므로 SUBMITTING으로 둔다
                row.submitFailed("CORE_REJECTED: " + errorName(e.getDetails()));
                queue.save(row);
            }
            throw e;
        }

        PublicationQueue saved = tx().execute(status -> {
            PublicationQueue r = queue.findById(row.getId()).orElseThrow();
            r.accepted(pub.publicationId(), pub.status() == null ? PublicationQueue.PENDING : pub.status(),
                    pub.version(), parseTime(pub.decisionRequiredBy()));
            AnalysisReport rep = reportRepository.findById(reportId).orElseThrow();
            rep.markPending(pub.publicationId(), contentHash);
            return queue.save(r);
        });

        auditService.record("PUBLICATION_SUBMITTED", userId, null, request.getId(), Map.of(
                "publicationId", pub.publicationId(), "reportId", reportId,
                "corpCode", row.getCorpCode(), "periodLabel", periodLabel,
                "contentHash", contentHash,
                "supersedesId", supersedesId == null ? "" : supersedesId,
                "duplicate", Boolean.TRUE.equals(pub.duplicate())));
        log.info("CORE_PUBLICATION_SUBMITTED user={} publication={} corp={} period={}",
                userId, pub.publicationId(), row.getCorpCode(), periodLabel);
        return PublicationDto.from(saved);
    }

    /**
     * 승인. 요청자 본인은 승인할 수 없다(4-eyes). Core도 같은 규칙(SELF_APPROVAL)을 갖지만
     * Spring이 먼저 막는다 — 원장까지 가서 거절당할 요청을 내보낼 이유가 없다.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public PublicationDto approve(String userId, String publicationId, String comment) {
        PublicationQueue row = find(publicationId);
        AnalysisReport report = reportRepository.findById(row.getReportId())
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트를 찾을 수 없음"));
        checkNotSelf(userId, row, report);

        CorePublicationDto pub;
        try {
            // 저장해 둔 content_hash를 보낸다. 원장이 접수 때 받은 값과 비교한다
            pub = core.approvePublication(publicationId, userId, row.getContentHash());
        } catch (ApiException e) {
            syncExpired(e, row, report);
            throw e;
        }

        row.applyDecision(pub.status() == null ? PublicationQueue.PUBLISHED : pub.status(),
                userId, parseTime(pub.decidedAt()), comment);
        row.applyVersion(pub.version());
        // 정정 발행이 승인되면 이전 건은 원장에서 SUPERSEDED가 된다. 사내 기록도 맞춘다
        if (row.getSupersedesId() != null) {
            queue.findByPublicationId(row.getSupersedesId())
                    .ifPresent(prev -> prev.markStatus(PublicationQueue.SUPERSEDED));
        }

        ObjectNode body = reportBody.parse(report.getBodyJson());
        reportBody.decide(body, "승인됨", userId, comment);
        reportBody.appendEvent(body, userId, "승인", null, comment == null ? "" : comment);
        report.markApproved(reportBody.write(body));

        auditService.record("PUBLICATION_APPROVED", userId, null, null, Map.of(
                "publicationId", publicationId, "reportId", row.getReportId(),
                "status", row.getStatus(), "version", row.getVersion() == null ? 0 : row.getVersion(),
                "submittedBy", row.getSubmittedBy()));
        log.info("CORE_PUBLICATION_PUBLISHED user={} publication={}", userId, publicationId);
        return PublicationDto.from(row);
    }

    @Transactional(noRollbackFor = ApiException.class)
    public PublicationDto reject(String userId, String publicationId, String reason) {
        PublicationQueue row = find(publicationId);
        AnalysisReport report = reportRepository.findById(row.getReportId())
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "리포트를 찾을 수 없음"));

        CorePublicationDto pub;
        try {
            pub = core.rejectPublication(publicationId, userId, reason);
        } catch (ApiException e) {
            syncExpired(e, row, report);
            throw e;
        }

        row.applyDecision(pub.status() == null ? PublicationQueue.REJECTED : pub.status(),
                userId, parseTime(pub.decidedAt()), reason);

        ObjectNode body = reportBody.parse(report.getBodyJson());
        reportBody.decide(body, "수정 요청", userId, reason);
        reportBody.appendEvent(body, userId, "반려", null, reason == null ? "" : reason);
        report.markRejected(reportBody.write(body));

        auditService.record("PUBLICATION_REJECTED", userId, null, null, Map.of(
                "publicationId", publicationId, "reportId", row.getReportId(),
                "reason", reason == null ? "" : reason));
        log.info("CORE_PUBLICATION_REJECTED user={} publication={} reason={}", userId, publicationId, reason);
        return PublicationDto.from(row);
    }

    @Transactional(readOnly = true)
    public List<PublicationDto> listPending() {
        return queue.findByStatusOrderByCreatedAtAsc(PublicationQueue.PENDING).stream()
                .map(PublicationDto::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<PublicationDto> search(String corpCode, String status, int limit) {
        return queue.search(blankToNull(corpCode), blankToNull(status),
                        PageRequest.of(0, Math.min(Math.max(limit, 1), 200))).stream()
                .map(PublicationDto::from)
                .toList();
    }

    // ── 내부 ──

    /** 발행을 요청한 사람, 그리고 분석을 요청한 사람 모두 자기 건을 승인할 수 없다. */
    void checkNotSelf(String userId, PublicationQueue row, AnalysisReport report) {
        String owner = requestRepository.findById(report.getRequestId())
                .map(AnalysisRequest::getUserId).orElse(null);
        if (userId.equals(row.getSubmittedBy()) || userId.equals(owner)) {
            throw new ApiException(ErrorCode.SELF_APPROVAL_FORBIDDEN,
                    "자기 요청은 승인할 수 없습니다",
                    Map.of("submittedBy", row.getSubmittedBy(), "requestOwner", owner == null ? "" : owner));
        }
    }

    /** 원장이 결재 기한 초과(EXPIRED)로 거절했으면 사내 기록도 맞추고 리포트 잠금을 푼다. */
    private void syncExpired(ApiException e, PublicationQueue row, AnalysisReport report) {
        if (e.getErrorCode() == ErrorCode.CORE_PUBLICATION_REJECTED && "EXPIRED".equals(errorName(e.getDetails()))) {
            row.markStatus(PublicationQueue.EXPIRED);
            report.backToDraft();
        }
    }

    private PublicationQueue find(String publicationId) {
        return queue.findByPublicationId(publicationId)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "결재 건을 찾지 못했다"));
    }

    private TransactionTemplate tx() {
        return new TransactionTemplate(transactionManager);
    }

    private static String errorName(Object details) {
        if (details instanceof Map<?, ?> m && m.get("error") != null) {
            return String.valueOf(m.get("error"));
        }
        return details == null ? "" : String.valueOf(details);
    }

    private static String blankToNull(String s) {
        return s == null || s.isBlank() ? null : s;
    }

    /** Core가 주는 시각(오프셋 있는 ISO 또는 없는 ISO)을 서울 기준 LocalDateTime으로 맞춘다. */
    static LocalDateTime parseTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(value).atZoneSameInstant(SEOUL).toLocalDateTime();
        } catch (Exception ignored) {
            // 오프셋 없는 형식
        }
        try {
            return LocalDateTime.parse(value);
        } catch (Exception ignored) {
            return null;
        }
    }
}
