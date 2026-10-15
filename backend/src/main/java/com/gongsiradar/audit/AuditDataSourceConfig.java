package com.gongsiradar.audit;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 감사 기록 전용 커넥션.
 * <p>
 * {@code gongsi_audit} 계정은 {@code audit_log}·{@code guardrail_event}·
 * {@code agent_tool_call_log}에 <b>INSERT와 SELECT만</b> 가진다. UPDATE·DELETE는
 * 아예 부여하지 않았으므로, 이 커넥션으로는 감사 로그를 고칠 수 없다.
 * append-only를 애플리케이션 코드가 아니라 <b>DB 권한이 보장</b>한다.
 * <p>
 * 왜 커넥션을 나누는가. 기존 {@code spring.datasource}는 애플리케이션 계정이라 UPDATE가
 * 된다. 그 커넥션으로 감사 로그를 쓰면 "고칠 수 있는 경로로 기록한다"는 뜻이 되고,
 * 그러면 통제가 코드 리뷰에만 기대게 된다. Core Zone의 조회 키와 시스템 키를 나눈 것과 같은 사상이다.
 * <p>
 * [주의] {@code DataSource} 타입 빈을 직접 만들면 Spring Boot의 자동 설정이 물러난다
 * ({@code @ConditionalOnMissingBean}). 그래서 여기서는 {@code HikariDataSource}를
 * 빈으로 노출하지 않고 {@code JdbcTemplate} 안에 감춘다 — 기존 JPA 설정을 건드리지 않는다.
 * <p>
 * 읽기는 이 커넥션을 쓰지 않는다. {@code AuditLogController}·{@code AdminController}의
 * 조회는 기존 JPA 경로를 그대로 쓴다. 읽는 데는 특별한 권한이 필요 없다.
 */
@Configuration
public class AuditDataSourceConfig {

    @Bean
    public JdbcTemplate auditJdbcTemplate(
            @Value("${gongsi.audit.url}") String url,
            @Value("${gongsi.audit.username}") String username,
            @Value("${gongsi.audit.password}") String password) {

        HikariDataSource ds = new HikariDataSource();
        ds.setJdbcUrl(url);
        ds.setUsername(username);
        ds.setPassword(password);
        ds.setDriverClassName("org.mariadb.jdbc.Driver");
        ds.setPoolName("audit-pool");
        // 감사 기록은 요청당 한두 건이라 커넥션을 많이 잡을 이유가 없다
        ds.setMaximumPoolSize(3);
        return new JdbcTemplate(ds);
    }
}
