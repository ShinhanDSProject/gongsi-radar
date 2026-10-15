package com.gongsiradar.auth;

import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtProvider jwtProvider;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            String token = header.substring(7);
            try {
                Claims claims = jwtProvider.parse(token);
                // Refresh 토큰으로 API를 부르는 것은 막는다. 역할·Scope가 들어 있지 않은 토큰이다
                if (!JwtProvider.TYPE_ACCESS.equals(claims.get("typ", String.class))) {
                    throw new IllegalArgumentException("access 토큰이 아님");
                }
                String userId = claims.getSubject();
                String role = claims.get("role", String.class);
                @SuppressWarnings("unchecked")
                List<String> scopes = claims.get("scopes", List.class);

                List<SimpleGrantedAuthority> authorities = Stream.concat(
                        Stream.of(new SimpleGrantedAuthority("ROLE_" + role)),
                        (scopes == null ? List.<String>of() : scopes).stream()
                                .map(s -> new SimpleGrantedAuthority("SCOPE_" + s))
                ).collect(Collectors.toList());

                UsernamePasswordAuthenticationToken auth =
                        new UsernamePasswordAuthenticationToken(userId, null, authorities);
                SecurityContextHolder.getContext().setAuthentication(auth);
            } catch (Exception e) {
                SecurityContextHolder.clearContext();
            }
        }
        chain.doFilter(request, response);
    }
}
