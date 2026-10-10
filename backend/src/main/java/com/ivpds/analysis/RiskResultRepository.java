package com.ivpds.analysis;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Truy cập dữ liệu bảng {@code risk_results} (kèm {@code risk_indicators}). */
public interface RiskResultRepository extends JpaRepository<RiskResult, UUID> {

    /** Kết quả đánh giá rủi ro của một lần phân tích. */
    Optional<RiskResult> findByAnalysisId(UUID analysisId);
}
