package com.gongsiradar.ingest.service;

import com.gongsiradar.ingest.repository.IngestStore;

import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.web.RequestContext;
import com.gongsiradar.data.config.DataSourceConfig;
import com.gongsiradar.data.source.RadarSource;
import com.gongsiradar.data.support.Rows;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 일일 수집 실행기. 예약 작업({@code gongsi.ingest.cron})과 1회 실행 모드({@code --gongsi.ingest.run-once=daily|backfill})가
 * 이 클래스를 부른다. <b>HTTP로 수집을 시작하는 경로는 없다</b> — 요청을 받는 경로가 원천 호출 예산과 적재 쓰기를 움직이지
 * 못하게 한다(관리 화면은 상태 조회만).
 * <p>
 * 쓰기는 수집 전용 계정({@code gongsi.ingest.datasource}, gongsi_ingest: 적재 테이블 SELECT·INSERT·UPDATE, kill_switch_status
 * SELECT만)으로 한다. 감사 기록과 같은 이유로 DataSource를 빈으로 노출하지 않고 이 안에 감춘다 — 다른 코드가 실수로 이
 * 커넥션을 주입받지 못하고, Spring Boot의 기본 DataSource 자동 설정도 물러나지 않는다. 풀은 첫 수집 때 연결한다.
 * <p>
 * 실행마다 {@code audit_log}에 {@code INGEST_RUN} 한 줄(단계별 상태·호출 수·행 수, 키·본문 없음)을 감사 전용 경로로 남긴다.
 * request_uid는 실행 ID(run_uid)다.
 */
@Slf4j
@Service
public class IngestService {

    private final RadarSource origin;
    private final AuditService auditService;
    private final Clock clock;
    private final HikariDataSource ingestDataSource;
    private final IngestStore store;
    private final int budget;
    private final int years;
    private final boolean documents;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public IngestService(@Qualifier("originSource") RadarSource origin, AuditService auditService, Clock clock,
                         @Value("${gongsi.ingest.datasource.url}") String url,
                         @Value("${gongsi.ingest.datasource.username}") String username,
                         @Value("${gongsi.ingest.datasource.password}") String password,
                         @Value("${gongsi.ingest.budget:15000}") int budget,
                         @Value("${gongsi.ingest.years:3}") int years,
                         @Value("${gongsi.ingest.documents:true}") boolean documents) {
        this.origin = origin;
        this.auditService = auditService;
        this.clock = clock;
        HikariDataSource ds = new HikariDataSource();
        ds.setJdbcUrl(url);
        ds.setUsername(username);
        ds.setPassword(password);
        ds.setPoolName("ingest-pool");
        ds.setMaximumPoolSize(2);       // 수집은 한 번에 하나만 돈다
        ds.setMinimumIdle(0);
        this.ingestDataSource = ds;
        this.store = new IngestStore(ds);
        this.budget = budget;
        this.years = years;
        this.documents = documents;
    }

    @PreDestroy
    void close() {
        ingestDataSource.close();
    }

    /** 예약 실행. cron이 비어 있거나 "-"면 꺼져 있다(기본). 예: {@code GONGSI_INGEST_CRON="0 30 18 * * MON-FRI"} */
    @Scheduled(cron = "${gongsi.ingest.cron:-}", zone = "Asia/Seoul")
    public void scheduled() {
        run("daily");
    }

    /** 한 번 돌린다. 이미 도는 중이면 null(겹쳐 돌지 않는다). */
    public Ingestor.RunReport run(String mode) {
        if (!"daily".equals(mode) && !"backfill".equals(mode)) {
            throw new IllegalArgumentException("수집 모드는 daily 또는 backfill: " + mode);
        }
        if (!running.compareAndSet(false, true)) {
            log.warn("수집이 이미 진행 중이라 이번 실행({})은 건너뜁니다", mode);
            return null;
        }
        String prevUid = RequestContext.get();
        try {
            log.info("수집 시작: {} · 원천 {} · 예산 {}회 · DB {}", mode, origin.name(), budget, ingestDataSource.getJdbcUrl());
            Ingestor ing = new Ingestor(origin, store, budget, LocalDate.now(clock),
                    () -> LocalDateTime.now(DataSourceConfig.ZONE),
                    r -> log.info("  {} {} 호출 {} · 행 {}{}{}", r.step, r.status, r.calls, r.rows,
                            r.remaining > 0 ? " · 남음 " + r.remaining : "", r.error != null ? " · " + r.error : ""));
            Ingestor.RunReport rep = ing.run(mode, Ingestor.STEPS, years, documents);
            audit(rep);
            log.info("수집 끝: {} · 호출 {}회 · {}", rep.runUid(), rep.calls(), rep.summary());
            return rep;
        } finally {
            if (prevUid == null) RequestContext.clear();
            else RequestContext.set(prevUid);
            running.set(false);
        }
    }

    /** 감사 로그 INGEST_RUN. 키 값·응답 본문은 남기지 않는다 — 단계별 상태·호출 수·행 수·실패 사유만. */
    private void audit(Ingestor.RunReport rep) {
        List<Map<String, Object>> steps = new ArrayList<>();
        for (Ingestor.StepResult s : rep.steps()) {
            String err = s.error == null ? "" : s.error;
            steps.add(Rows.m("step", s.step, "status", s.status, "calls", s.calls, "rows", s.rows,
                    "remaining", s.remaining, "error", err.substring(0, Math.min(200, err.length()))));
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("runUid", rep.runUid());
        payload.put("mode", rep.mode());
        payload.put("source", origin.name());
        payload.put("calls", rep.calls());
        payload.put("steps", steps);
        RequestContext.set(rep.runUid());
        auditService.record("INGEST_RUN", "system", "ingest", null, payload);
    }
}
