package com.gongsiradar.data.config;

import com.gongsiradar.data.client.SourceHttp;
import com.gongsiradar.data.source.DataSourceException;
import com.gongsiradar.data.source.IngestedDataSource;
import com.gongsiradar.data.source.OpenDartDataSource;
import com.gongsiradar.data.source.RadarSource;
import com.gongsiradar.data.source.SampleDataSource;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import javax.sql.DataSource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneId;

/**
 * 데이터 소스 구성. {@code gongsi.data.source=sample|opendart}(기본 sample).
 * <ul>
 *   <li>{@code originSource}: 원천 그대로. 일일 수집 작업은 항상 이것을 쓴다</li>
 *   <li>{@code radarSource}(@Primary): 적재 DB를 먼저 읽고 없으면 원천 — 화면 API·내부 데이터 API가 쓴다</li>
 * </ul>
 * 원천 API 키(OPENDART_API_KEY·DATA_GO_KR_API_KEY)는 Spring에만 둔다. AI 서버는 내부 데이터 API로만 받는다.
 */
@Slf4j
@Configuration
public class DataSourceConfig {

    public static final ZoneId ZONE = ZoneId.of("Asia/Seoul");

    /** 업무 날짜 기준(한국 시간). 테스트는 고정 시계로 바꾼다. */
    @Bean
    public Clock clock() {
        return Clock.system(ZONE);
    }

    @Bean("originSource")
    public RadarSource originSource(
            @Value("${gongsi.data.source:sample}") String mode,
            @Value("${gongsi.data.sample-dir:../samples/data}") String sampleDir,
            @Value("${gongsi.data.cache-dir:.cache}") String cacheDir,
            @Value("${gongsi.data.opendart-api-key:}") String dartKey,
            @Value("${gongsi.data.data-go-kr-api-key:}") String goKey,
            @Value("${gongsi.data.peers-file:}") String peersFile,
            @Value("${gongsi.data.opendart-min-interval-ms:700}") long minIntervalMs,
            @Value("${gongsi.data.opendart-cooldown-sec:300}") long cooldownSec,
            Clock clock) {
        if ("opendart".equalsIgnoreCase(mode)) {
            log.info("데이터 소스: OpenDART (캐시 {})", Path.of(cacheDir).toAbsolutePath().normalize());
            return new OpenDartDataSource(dartKey, goKey, Path.of(cacheDir), peersFile.isBlank() ? null : Path.of(peersFile),
                    SourceHttp.jdk(), clock, Duration.ofSeconds(1), Duration.ofMillis(minIntervalMs), Duration.ofSeconds(cooldownSec));
        }
        if (!"sample".equalsIgnoreCase(mode)) {
            throw new IllegalStateException("gongsi.data.source는 sample 또는 opendart: " + mode);
        }
        Path dir = resolveSampleDir(sampleDir);
        log.info("데이터 소스: 샘플 ({})", dir);
        return new SampleDataSource(dir);
    }

    @Bean
    @Primary
    public RadarSource radarSource(@Qualifier("originSource") RadarSource origin, DataSource appDataSource,
                                   @Value("${gongsi.data.ingested-read:true}") boolean ingestedRead, Clock clock) {
        return ingestedRead ? new IngestedDataSource(origin, appDataSource, clock) : origin;
    }

    /**
     * 샘플 디렉터리 찾기. 설정값이 상대 경로라 실행 위치(backend/ 또는 저장소 루트·IDE)에 따라 달라질 수 있어,
     * 설정 경로에 list.json이 없으면 현재 위치에서 위로 올라가며 {@code samples/data}를 찾는다.
     */
    public static Path resolveSampleDir(String configured) {
        Path p = Path.of(configured).toAbsolutePath().normalize();
        if (Files.exists(p.resolve("list.json"))) {
            return p;
        }
        Path cur = Path.of("").toAbsolutePath();
        for (int i = 0; i < 4 && cur != null; i++, cur = cur.getParent()) {
            Path cand = cur.resolve("samples").resolve("data");
            if (Files.exists(cand.resolve("list.json"))) {
                return cand;
            }
        }
        throw new DataSourceException("샘플 데이터가 없습니다: " + p + " (gongsi.data.sample-dir 확인, 저장소 루트에서 python samples/build_samples.py 실행)");
    }
}
