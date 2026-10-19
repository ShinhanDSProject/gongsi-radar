package com.gongsiradar.glossary.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface GlossaryTermRepository extends JpaRepository<GlossaryTerm, Long> {

    List<GlossaryTerm> findByStatusOrderByTermAsc(String status);

    List<GlossaryTerm> findAllByOrderByUpdatedAtDesc();

    Optional<GlossaryTerm> findByTerm(String term);
}
