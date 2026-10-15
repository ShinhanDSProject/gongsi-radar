package com.gongsiradar.report;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

public interface AnalysisReportRepository extends JpaRepository<AnalysisReport, Long> {

    Optional<AnalysisReport> findByRequestId(Long requestId);

    /** ownerId가 null이면 전체(Senior), 값이 있으면 그 사람이 낸 분석 요청의 리포트만(Junior). */
    @Query(value = "select r from AnalysisReport r "
            + "where (:status is null or r.approvalStatus = :status) "
            + "and (:ownerId is null or r.requestId in "
            + "     (select q.id from AnalysisRequest q where q.userId = :ownerId)) "
            + "order by r.id desc",
            countQuery = "select count(r) from AnalysisReport r "
            + "where (:status is null or r.approvalStatus = :status) "
            + "and (:ownerId is null or r.requestId in "
            + "     (select q.id from AnalysisRequest q where q.userId = :ownerId))")
    Page<AnalysisReport> search(ApprovalStatus status, String ownerId, Pageable pageable);
}
