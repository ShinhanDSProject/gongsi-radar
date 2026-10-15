package com.gongsiradar.ingest.runner;

import com.gongsiradar.ingest.service.IngestService;
import com.gongsiradar.ingest.service.Ingestor;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

/**
 * 1회 실행 모드. {@code ./gradlew bootRun --args='--gongsi.ingest.run-once=daily'}(또는 backfill)이면 수집을 한 번 돌리고
 * 끝낸다. 이때 웹 서버는 띄우지 않는다({@code GongsiRadarApplication} 참고) — 8180에서 돌고 있는 서버와 겹치지 않는다.
 * <p>
 * 종료 코드: 0 정상(PARTIAL 포함), 1 실패한 단계가 있음, 2 잘못된 모드·이미 실행 중.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class IngestRunOnce implements ApplicationRunner, ExitCodeGenerator {

    private final IngestService ingestService;

    @Value("${gongsi.ingest.run-once:}")
    private String mode;

    private boolean executed;
    private int exitCode;

    @Override
    public void run(ApplicationArguments args) {
        if (mode == null || mode.isBlank()) {
            return;
        }
        executed = true;
        try {
            Ingestor.RunReport rep = ingestService.run(mode.strip());
            if (rep == null) {
                exitCode = 2;
            } else {
                exitCode = rep.steps().stream().anyMatch(s -> "FAILED".equals(s.status)) ? 1 : 0;
                System.out.println("끝: 호출 " + rep.calls() + "회 · " + rep.runUid() + " · " + rep.summary());
            }
        } catch (IllegalArgumentException e) {
            log.error(e.getMessage());
            exitCode = 2;
        }
    }

    public boolean executed() {
        return executed;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
