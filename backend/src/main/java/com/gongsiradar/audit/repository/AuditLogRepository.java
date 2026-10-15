package com.gongsiradar.audit.repository;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

/**
 * 조회와 저장만 노출한다.
 * <p>
 * {@code JpaRepository}가 {@code delete*}를 딸려 주긴 하지만 서비스에서 부르지 않고,
 * 실수로 불러도 애플리케이션 계정(gongsi_app)에 감사 테이블 쓰기 권한이 없어 DB가 막는다. 통제는 한 겹으로 두지 않는다.
 */
public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    List<AuditLog> findByRequestUidOrderByIdAsc(String requestUid);

    @Query("select a from AuditLog a where (:type is null or a.type = :type) order by a.id desc")
    List<AuditLog> search(String type, Pageable pageable);
}
