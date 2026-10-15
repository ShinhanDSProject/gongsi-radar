package com.gongsiradar.admin;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface GuardrailEventRepository extends JpaRepository<GuardrailEvent, Long> {

    @Query("select g from GuardrailEvent g "
            + "where (:severity is null or g.severity = :severity) order by g.id desc")
    List<GuardrailEvent> search(String severity, Pageable pageable);
}
