package com.ivpds.analysis;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Kết quả đánh giá rủi ro của một lần phân tích (bảng {@code risk_results}), kèm các dấu hiệu lừa đảo
 * tìm thấy (bảng {@code risk_indicators}). Mọi giá trị ở đây đều do AI service trả về.
 */
@Entity
@Table(name = "risk_results")
public class RiskResult {

    /** Mức rủi ro của cuộc gọi. */
    public enum Level {
        LOW, MEDIUM, HIGH
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "analysis_id", nullable = false, updatable = false)
    private UUID analysisId;

    /** Điểm rủi ro từ 0 đến 100. */
    @JdbcTypeCode(SqlTypes.SMALLINT)
    @Column(name = "risk_score", nullable = false)
    private int riskScore;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", nullable = false, length = 10)
    private Level riskLevel;

    /** Mức chắc chắn của kết quả (0 đến 1); không phải xác suất lừa đảo. */
    @Column(precision = 5, scale = 4)
    private BigDecimal confidence;

    /** Xác suất lừa đảo do NLP Model tính (0 đến 1). */
    @Column(name = "model_probability", precision = 7, scale = 6)
    private BigDecimal modelProbability;

    @Column(name = "nlp_model_version", length = 100)
    private String nlpModelVersion;

    @Column(name = "ruleset_version", length = 30)
    private String rulesetVersion;

    @Column(name = "risk_engine_version", length = 30)
    private String riskEngineVersion;

    /** Mã các dấu hiệu lừa đảo (ví dụ OTP_REQUEST); mỗi mã một dòng trong {@code risk_indicators}. */
    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "risk_indicators", joinColumns = @JoinColumn(name = "risk_result_id"))
    @Column(name = "indicator_code", nullable = false, length = 50)
    private Set<String> indicators = new LinkedHashSet<>();

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected RiskResult() {
    }

    public RiskResult(UUID analysisId, int riskScore, Level riskLevel, BigDecimal confidence,
            BigDecimal modelProbability, Collection<String> indicators, String nlpModelVersion,
            String rulesetVersion, String riskEngineVersion) {
        this.analysisId = analysisId;
        this.riskScore = riskScore;
        this.riskLevel = riskLevel;
        this.confidence = confidence;
        this.modelProbability = modelProbability;
        this.indicators.addAll(indicators);
        this.nlpModelVersion = nlpModelVersion;
        this.rulesetVersion = rulesetVersion;
        this.riskEngineVersion = riskEngineVersion;
        this.createdAt = Instant.now();
    }

    public UUID getAnalysisId() {
        return analysisId;
    }

    public int getRiskScore() {
        return riskScore;
    }

    public Level getRiskLevel() {
        return riskLevel;
    }

    public BigDecimal getConfidence() {
        return confidence;
    }

    public BigDecimal getModelProbability() {
        return modelProbability;
    }

    public String getNlpModelVersion() {
        return nlpModelVersion;
    }

    public String getRulesetVersion() {
        return rulesetVersion;
    }

    public String getRiskEngineVersion() {
        return riskEngineVersion;
    }

    public Set<String> getIndicators() {
        return indicators;
    }
}
