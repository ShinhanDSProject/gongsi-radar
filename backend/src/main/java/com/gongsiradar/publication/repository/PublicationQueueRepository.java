package com.gongsiradar.publication.repository;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface PublicationQueueRepository extends JpaRepository<PublicationQueue, Long> {

    Optional<PublicationQueue> findByPublicationId(String publicationId);

    List<PublicationQueue> findByStatusOrderByCreatedAtAsc(String status);

    /** 정정 발행 판단용: 같은 회사·기간에서 가장 최근에 PUBLISHED 된 건. */
    Optional<PublicationQueue> findFirstByCorpCodeAndPeriodLabelAndStatusOrderByIdDesc(
            String corpCode, String periodLabel, String status);

    /** 응답을 못 받고 끊긴 접수 시도. 같은 내용이면 같은 멱등성 키로 다시 보낸다. */
    Optional<PublicationQueue> findFirstByReportIdAndContentHashAndStatusOrderByIdDesc(
            Long reportId, String contentHash, String status);

    @Query("select p from PublicationQueue p "
            + "where (:corpCode is null or p.corpCode = :corpCode) "
            + "and (:status is null or p.status = :status) "
            + "order by p.id desc")
    List<PublicationQueue> search(String corpCode, String status, Pageable pageable);
}
