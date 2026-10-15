package com.gongsiradar.admin.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface KillSwitchRepository extends JpaRepository<KillSwitchStatus, Long> {

    /** 최신 한 줄이 현재 상태다. FastAPI도 같은 기준으로 읽는다. */
    Optional<KillSwitchStatus> findFirstByOrderByIdDesc();
}
