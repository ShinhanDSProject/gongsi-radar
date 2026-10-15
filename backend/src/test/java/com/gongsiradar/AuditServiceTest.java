package com.gongsiradar;

import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.util.Hashing;
import com.gongsiradar.common.web.RequestContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/** 감사 로그 해시 체인. AI 서버와 같은 규칙(키 정렬 JSON, SHA-256 hex, 직전 행의 payload_hash)인지 확인한다. */
@SpringBootTest
class AuditServiceTest {

    @Autowired AuditService auditService;
    @Autowired JdbcTemplate auditJdbcTemplate;

    @AfterEach
    void clear() {
        RequestContext.clear();
    }

    @Test
    void payload는_키_정렬_JSON이고_prev_hash가_직전_행을_가리킨다() {
        String uid = "test-chain-" + UUID.randomUUID();
        RequestContext.set(uid);
        auditService.record("TEST_CHAIN", "tester", Map.of("b", 2, "a", 1));
        auditService.record("TEST_CHAIN", "tester", Map.of("z", "last"));

        List<Map<String, Object>> rows = auditJdbcTemplate.queryForList(
                "SELECT id, payload_json, payload_hash, prev_hash FROM audit_log WHERE request_uid = ? ORDER BY id", uid);
        assertThat(rows).hasSize(2);

        String json = (String) rows.get(0).get("payload_json");
        assertThat(json).isEqualTo("{\"a\":1,\"b\":2}");
        assertThat(rows.get(0).get("payload_hash")).isEqualTo(Hashing.sha256Hex(json));

        // 두 번째 행의 prev_hash = 그 직전 행(id-1 이하 최댓값)의 payload_hash.
        // 다른 프로세스(AI 서버)가 사이에 썼을 수 있으므로 "바로 앞 id의 행"과 비교한다
        Long secondId = ((Number) rows.get(1).get("id")).longValue();
        String expectedPrev = auditJdbcTemplate.queryForObject(
                "SELECT payload_hash FROM audit_log WHERE id < ? ORDER BY id DESC LIMIT 1", String.class, secondId);
        assertThat(rows.get(1).get("prev_hash")).isEqualTo(expectedPrev);
    }
}
