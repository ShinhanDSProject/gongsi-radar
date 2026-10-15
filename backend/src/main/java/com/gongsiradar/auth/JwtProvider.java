package com.gongsiradar.auth;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.List;

/**
 * Access·Refresh 토큰 발급과 검증.
 * <p>
 * 두 토큰은 {@code typ} 클레임으로 구분한다. Refresh 토큰에는 역할·Scope를 넣지 않는다 —
 * 재발급할 때 DB에서 다시 읽어야 권한 회수가 반영된다. 그래서 Refresh 토큰으로는 API를 부를 수 없다.
 */
@Component
public class JwtProvider {

    public static final String TYPE_ACCESS = "access";
    public static final String TYPE_REFRESH = "refresh";

    private final SecretKey key;
    private final long expireMinutes;
    private final long refreshExpireDays;

    public JwtProvider(@Value("${gongsi.jwt.secret}") String secret,
                       @Value("${gongsi.jwt.expire-minutes}") long expireMinutes,
                       @Value("${gongsi.jwt.refresh-expire-days}") long refreshExpireDays) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expireMinutes = expireMinutes;
        this.refreshExpireDays = refreshExpireDays;
    }

    public String createAccessToken(String userId, String name, String role, List<String> scopes) {
        Date now = new Date();
        Date expiry = new Date(now.getTime() + expireMinutes * 60 * 1000L);

        return Jwts.builder()
                .subject(userId)
                .claim("typ", TYPE_ACCESS)
                .claim("name", name)
                .claim("role", role)
                .claim("scopes", scopes)
                .issuedAt(now)
                .expiration(expiry)
                .signWith(key)
                .compact();
    }

    public String createRefreshToken(String userId) {
        Date now = new Date();
        Date expiry = new Date(now.getTime() + refreshExpireDays * 24 * 60 * 60 * 1000L);

        return Jwts.builder()
                .subject(userId)
                .claim("typ", TYPE_REFRESH)
                .issuedAt(now)
                .expiration(expiry)
                .signWith(key)
                .compact();
    }

    public Claims parse(String token) {
        return Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }
}
