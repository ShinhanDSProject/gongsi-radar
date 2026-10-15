package com.gongsiradar.analysis;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface AnalysisRequestRepository extends JpaRepository<AnalysisRequest, Long> {

    /** userId가 null이면 전체(Senior), 값이 있으면 그 사람 것만(Junior). */
    @Query("select r from AnalysisRequest r "
            + "where (:userId is null or r.userId = :userId) "
            + "and (:status is null or r.status = :status) "
            + "order by r.id desc")
    Page<AnalysisRequest> search(String userId, AnalysisRequestStatus status, Pageable pageable);
}
