package com.gongsiradar.audit.repository;

import com.gongsiradar.audit.service.AuditService;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.Immutable;

import java.time.LocalDateTime;

/**
 * 감사 로그. <b>조회 전용 매핑이다.</b>
 * <p>
 * 쓰기는 {@link AuditService}가 감사 전용 커넥션으로 직접 INSERT한다. 여기로는 넣지 않는다.
 * {@code @Immutable}을 붙여 Hibernate가 UPDATE 문을 만들 수 없게 막고, setter도 빌더도 두지 않는다.
 * <p>
 * {@code BaseEntity}를 상속하지 않는다. 감사 로그에는 {@code updated_at}이 없어야 한다 —
 * 수정 시각이 있다는 건 수정할 수 있다는 뜻이고, 그러면 감사 로그가 아니다.
 * <p>
 * 진짜 통제는 DB 권한에 있다. {@code gongsi_audit} 계정에 UPDATE·DELETE를 주지 않았고,
 * 코드에 붙인 {@code @Immutable}은 그 위에 얹은 두 번째 겹이다.
 */
@Entity
@Getter
@Immutable
@Table(name = "audit_log")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String type;

    /** 요청 상관관계 ID. FastAPI·Core Zone의 기록과 이 값으로 이어진다. */
    @Column(name = "request_uid", length = 64)
    private String requestUid;

    @Column(name = "user_id", length = 64)
    private String userId;

    @Column(name = "agent_id", length = 64)
    private String agentId;

    @Column(name = "request_id")
    private Long requestId;

    @Column(name = "payload_json", nullable = false, columnDefinition = "JSON")
    private String payloadJson;

    @Column(name = "payload_hash", length = 64)
    private String payloadHash;

    @Column(name = "prev_hash", length = 64)
    private String prevHash;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;
}
