package com.gongsiradar;

import com.gongsiradar.ingest.runner.IngestRunOnce;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.scheduling.annotation.EnableScheduling;

import java.util.Arrays;

@EnableJpaAuditing
@EnableScheduling                       // 일일 수집 예약(gongsi.ingest.cron, 기본 꺼짐)
@SpringBootApplication
public class GongsiRadarApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(GongsiRadarApplication.class);
        // 수집 1회 실행 모드: 웹 서버 없이 수집만 돌리고 끝낸다(8180에서 도는 서버와 겹치지 않게)
        String env = System.getenv("GONGSI_INGEST_RUN_ONCE");
        boolean runOnce = Arrays.stream(args).anyMatch(a -> a.startsWith("--gongsi.ingest.run-once="))
                || (env != null && !env.isBlank());
        if (runOnce) {
            app.setWebApplicationType(WebApplicationType.NONE);
        }
        ConfigurableApplicationContext ctx = app.run(args);
        IngestRunOnce once = ctx.getBean(IngestRunOnce.class);
        if (once.executed()) {
            System.exit(SpringApplication.exit(ctx, once));
        }
    }

}
