package com.gongsiradar.audit;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.gongsiradar.common.Hashing;
import com.gongsiradar.common.RequestContext;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * 감사 기록. 사람의 행위를 남긴다.
 * <p>
 * Agent의 행위(Tool 호출, 가드레일 차단)는 FastAPI가 같은 테이블에 직접 넣는다.
 * 한쪽으로 몰지 않는 이유는 단순하다 — 기록은 그 일을 실제로 한 쪽이 남겨야 한다.
 * 남이 대신 신고해 주는 구조는 감사에서 성립하지 않는다.
 * <p>
 * JPA가 아니라 감사 전용 {@link JdbcTemplate}으로 쓴다({@link AuditDataSourceConfig}).
 * 이 커넥션의 계정에는 UPDATE·DELETE 권한이 없어서 <b>고칠 수 없는 경로로만 기록된다.</b>
 * 조회는 {@code AuditLogRepository}(기존 JPA)가 맡는다 — 쓰기와 읽기의 자격 증명이 다르다.
 * <p>
 * 트랜잭션을 따로 걸지 않는다. 커넥션 자체가 다르므로 본래 작업이 롤백돼도
 * "시도했다"는 기록은 그대로 남는다. {@code REQUIRES_NEW}가 하던 일을 커넥션 분리가 대신한다.
 * <p>
 * <b>해시 체인.</b> AI 서버와 같은 규칙으로 쓴다 —
 * {@code payload_json}은 키 정렬 JSON, {@code payload_hash = SHA-256(hex)(payload_json 문자열)},
 * {@code prev_hash}는 같은 감사 커넥션에서 읽은 직전 행(id 최댓값)의 {@code payload_hash}.
 * 중간 행을 고치거나 빼면 다음 행의 prev_hash와 어긋나 드러난다.
 * <p>
 * [한계] 같은 프로세스 안에서는 {@code synchronized}로 "직전 해시 읽기 → INSERT"를 직렬화한다.
 * 그러나 {@code gongsi_audit} 계정은 INSERT·SELECT만 있어 {@code SELECT ... FOR UPDATE}(행 잠금)를 쓸 수 없고,
 * AI 서버(다른 프로세스)도 같은 테이블에 쓴다. 두 프로세스가 거의 동시에 쓰면 둘 다 같은 직전 해시를 읽어
 * 체인이 드물게 갈라질 수 있다(같은 prev_hash를 가진 두 행). 검증 도구는 이를 변조가 아니라
 * "분기"로 구분해 보고해야 한다. 완전히 막으려면 감사 기록을 한 프로세스(또는 큐)로 모아야 한다.
 */
@Slf4j
@Service
public class AuditService {

    private static final String INSERT_SQL = """
            INSERT INTO audit_log
                (type, request_uid, user_id, agent_id, request_id, payload_json, payload_hash, prev_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """;

    private static final String LAST_HASH_SQL =
            "SELECT payload_hash FROM audit_log ORDER BY id DESC LIMIT 1";

    private final JdbcTemplate auditJdbcTemplate;

    /** 키 정렬 JSON 전용 매퍼. 같은 내용이면 항상 같은 문자열 → 같은 해시가 나와야 한다. */
    private final JsonMapper canonicalMapper = JsonMapper.builder()
            .findAndAddModules()
            .configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true)
            .configure(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY, true)
            .configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false)
            .build();

    public AuditService(JdbcTemplate auditJdbcTemplate) {
        this.auditJdbcTemplate = auditJdbcTemplate;
    }

    public void record(String type, String userId, Map<String, Object> payload) {
        record(type, userId, null, null, payload);
    }

    public void record(String type, String userId, String agentId, Long requestId,
                       Map<String, Object> payload) {
        try {
            String json = canonicalMapper.writeValueAsString(payload == null ? Map.of() : payload);
            String hash = Hashing.sha256Hex(json);
            append(type, RequestContext.get(), userId, agentId, requestId, json, hash);
        } catch (Exception e) {
            // [주의] 감사 기록 실패로 본래 작업을 되돌리지 않는다. 대신 실패 사실은 남긴다
            log.error("audit_log 기록 실패: type={}", type, e);
        }
    }

    /** 직전 해시 읽기와 INSERT 사이에 이 프로세스의 다른 기록이 끼어들지 못하게 한다. */
    private synchronized void append(String type, String uid, String userId, String agentId,
                                     Long requestId, String json, String hash) {
        auditJdbcTemplate.update(INSERT_SQL,
                type, uid, userId, agentId, requestId, json, hash, lastHash());
    }

    private String lastHash() {
        try {
            return auditJdbcTemplate.queryForObject(LAST_HASH_SQL, String.class);
        } catch (EmptyResultDataAccessException e) {
            return null;   // 첫 기록
        }
    }
}
