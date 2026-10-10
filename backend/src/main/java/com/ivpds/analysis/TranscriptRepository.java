package com.ivpds.analysis;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Truy cập dữ liệu bảng {@code transcripts}. */
public interface TranscriptRepository extends JpaRepository<Transcript, UUID> {

    /** Transcript của một lần phân tích. */
    Optional<Transcript> findByAnalysisId(UUID analysisId);
}
