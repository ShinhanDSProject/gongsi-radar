package com.gongsiradar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@EnableJpaAuditing
@SpringBootApplication
public class GongsiRadarApplication {

    public static void main(String[] args) {
        SpringApplication.run(GongsiRadarApplication.class, args);
    }

}
