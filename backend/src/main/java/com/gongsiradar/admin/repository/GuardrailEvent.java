package com.gongsiradar.admin.repository;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.Immutable;

import java.time.LocalDateTime;

/**
 * 가드레일 이벤트. FastAPI가 쓰고 Spring Boot는 읽기만 한다.
 * 
 * {@code @Immutable}을 붙여 Hibernate가 UPDATE를 만들지 못하게 막는다.
 * 필터를 실제로 돌린 쪽은 AI 서버이고, 여기서 고칠 수 있으면 기록의 주인이 흐려진다.
 * 
 * 원본 텍스트 컬럼이 없다. 걸러 낸 내용의 해시와 마스킹을 마친 결과만 남는다 —
 * 주민번호를 막은 기록에 주민번호가 들어 있으면 필터를 만든 의미가 없다.
 */
@Entity
@Getter
@Immutable
@Table(name = "guardrail_event")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class GuardrailEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 32)
    private String type;                  // INPUT, OUTPUT

    @Column(nullable = false, length = 16)
    private String severity;              // SAFE, WARNING, BLOCKED

    @Column(name = "request_uid", length = 64)
    private String requestUid;

    @Column(name = "user_id", length = 64)
    private String userId;

    @Column(name = "agent_id", length = 64)
    private String agentId;

    @Column(name = "request_id")
    private Long requestId;

    @Column(name = "detected_issues", nullable = false, columnDefinition = "JSON")
    private String detectedIssues;

    @Column(name = "payload_hash", nullable = false, length = 64)
    private String payloadHash;

    @Column(name = "filtered_text", columnDefinition = "TEXT")
    private String filteredText;

    @Column(nullable = false)
    private Boolean blocked;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;
}
