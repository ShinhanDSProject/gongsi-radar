package com.gongsiradar.user.repository;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "user_scopes",
        uniqueConstraints = @UniqueConstraint(columnNames = {"user_id", "scope"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class UserScope {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false, length = 64)
    private String scope;

    @Column(name = "granted_at", nullable = false)
    private LocalDateTime grantedAt;

    @Column(name = "expires_at")
    private LocalDateTime expiresAt;

    /** 만료 시각이 지난 Scope는 토큰에 넣지 않는다. 비어 있으면 무기한. */
    public boolean isValidAt(LocalDateTime now) {
        return expiresAt == null || expiresAt.isAfter(now);
    }
}
