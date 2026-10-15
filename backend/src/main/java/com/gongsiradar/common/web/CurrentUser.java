package com.gongsiradar.common.web;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;

/**
 * 현재 요청의 JWT에서 꺼낸 역할·Scope를 읽는 도우미.
 * <p>
 * {@code JwtAuthenticationFilter}가 권한을 {@code ROLE_*}·{@code SCOPE_*}로 심어 두었다.
 * 서비스 계층이 "Junior는 자기 것만, Senior는 전체"를 가릴 때 쓴다.
 * DB를 다시 읽지 않는다 — 토큰에 담긴 권한이 이 요청의 권한이다.
 */
public final class CurrentUser {

    private CurrentUser() {
    }

    public static boolean isSenior() {
        return hasAuthority("ROLE_SENIOR_MANAGER") || hasAuthority("ROLE_ADMIN");
    }

    public static List<String> scopes() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            return List.of();
        }
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(a -> a.startsWith("SCOPE_"))
                .map(a -> a.substring("SCOPE_".length()))
                .toList();
    }

    private static boolean hasAuthority(String authority) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return auth != null && auth.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
