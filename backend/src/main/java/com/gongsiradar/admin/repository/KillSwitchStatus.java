package com.gongsiradar.admin.repository;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Kill Switch 이력. 상태를 고치는 게 아니라 토글할 때마다 한 줄씩 쌓는다.
 * <p>
 * 최신 행 하나가 현재 상태다. UPDATE로 관리하면 "언제 누가 왜 껐다 켰나"가 사라진다.
 * 비상 정지에서 감사가 알고 싶은 건 지금 상태가 아니라 그 이력이다.
 */
@Entity
@Getter
@Table(name = "kill_switch_status")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class KillSwitchStatus {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Boolean active;

    @Column(length = 500)
    private String reason;

    @Column(name = "toggled_by", nullable = false, length = 64)
    private String toggledBy;

    @Column(name = "toggled_at", updatable = false)
    private LocalDateTime toggledAt;

    @Builder
    public KillSwitchStatus(Boolean active, String reason, String toggledBy) {
        this.active = active;
        this.reason = reason;
        this.toggledBy = toggledBy;
        // 응답의 since가 비지 않도록 애플리케이션에서 시각을 채운다(DB 기본값을 쓰면 저장 직후 엔티티에는 null이다)
        this.toggledAt = LocalDateTime.now();
    }
}
