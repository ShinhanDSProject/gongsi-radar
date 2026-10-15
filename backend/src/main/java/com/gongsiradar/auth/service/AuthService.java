package com.gongsiradar.auth.service;

import com.gongsiradar.auth.security.JwtProvider;

import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.auth.dto.LoginRequest;
import com.gongsiradar.auth.dto.LoginResponse;
import com.gongsiradar.auth.dto.RefreshResponse;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.user.repository.User;
import com.gongsiradar.user.repository.UserRepository;
import com.gongsiradar.user.repository.UserScope;
import com.gongsiradar.user.repository.UserScopeRepository;
import io.jsonwebtoken.Claims;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final UserScopeRepository userScopeRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtProvider jwtProvider;
    private final AuditService auditService;

    @Transactional(readOnly = true)
    public LoginResponse login(LoginRequest req) {
        User user = userRepository.findByUserId(req.userId()).orElse(null);
        if (user == null) {
            auditService.record("USER_LOGIN_FAILED", req.userId(), Map.of("reason", "UNKNOWN_USER"));
            throw new ApiException(ErrorCode.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다");
        }

        if (!user.isActive()) {
            auditService.record("USER_LOGIN_FAILED", req.userId(), Map.of("reason", "INACTIVE"));
            throw new ApiException(ErrorCode.UNAUTHORIZED, "비활성 사용자");
        }

        if (!passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            // 실패도 남긴다. 감사에서 더 중요한 쪽은 성공한 로그인이 아니라 실패한 시도다
            auditService.record("USER_LOGIN_FAILED", req.userId(), Map.of("reason", "BAD_PASSWORD"));
            throw new ApiException(ErrorCode.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다");
        }

        List<String> scopes = scopesOf(user);
        String accessToken = jwtProvider.createAccessToken(
                user.getUserId(), user.getName(), user.getRole().name(), scopes);
        String refreshToken = jwtProvider.createRefreshToken(user.getUserId());

        // 비밀번호도 토큰도 넣지 않는다. 누가 언제 들어왔고 무슨 권한이었는지면 된다
        auditService.record("USER_LOGIN", user.getUserId(),
                Map.of("role", user.getRole().name(), "scopes", scopes));

        return new LoginResponse(
                accessToken,
                refreshToken,
                new LoginResponse.UserInfo(user.getUserId(), user.getName(), user.getRole().name(), scopes)
        );
    }

    /**
     * Access 토큰 재발급. 역할·Scope는 토큰이 아니라 DB에서 다시 읽는다 —
     * 그 사이 권한이 회수됐거나 계정이 비활성화됐다면 새 토큰에 반영돼야 한다.
     */
    @Transactional(readOnly = true)
    public RefreshResponse refresh(String refreshToken) {
        Claims claims;
        try {
            claims = jwtProvider.parse(refreshToken);
        } catch (Exception e) {
            throw new ApiException(ErrorCode.UNAUTHORIZED, "유효하지 않은 refresh 토큰");
        }
        if (!JwtProvider.TYPE_REFRESH.equals(claims.get("typ", String.class))) {
            throw new ApiException(ErrorCode.UNAUTHORIZED, "refresh 토큰이 아님");
        }
        User user = userRepository.findByUserId(claims.getSubject())
                .filter(User::isActive)
                .orElseThrow(() -> new ApiException(ErrorCode.UNAUTHORIZED, "사용자 없음 또는 비활성"));

        return new RefreshResponse(jwtProvider.createAccessToken(
                user.getUserId(), user.getName(), user.getRole().name(), scopesOf(user)));
    }

    private List<String> scopesOf(User user) {
        LocalDateTime now = LocalDateTime.now();
        return userScopeRepository.findByUserId(user.getId()).stream()
                .filter(s -> s.isValidAt(now))
                .map(UserScope::getScope)
                .sorted()
                .toList();
    }
}
