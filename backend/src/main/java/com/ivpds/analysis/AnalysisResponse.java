package com.ivpds.analysis;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Trạng thái và kết quả của một lần phân tích, trả về cho chủ cuộc gọi.
 *
 * <p>Năm trường {@code transcript}, {@code riskScore}, {@code riskLevel}, {@code confidence} và
 * {@code indicators} theo đúng API contract trong README. Chúng là null cho tới khi có giá trị thật:
 * {@code transcript} có sau bước nhận dạng giọng nói, bốn trường còn lại chỉ có khi trạng thái là COMPLETED.
 * Một lần phân tích FAILED không bao giờ mang điểm hay mức rủi ro.
 *
 * @param errorCode    mã lỗi khi FAILED (ví dụ AI_SERVICE_UNAVAILABLE, INVALID_AUDIO, NO_SPEECH_DETECTED)
 * @param errorMessage thông báo lỗi cho người đọc
 * @param confidence   mức chắc chắn của kết quả (0 đến 1); không phải xác suất lừa đảo
 * @param indicators   mã các dấu hiệu lừa đảo tìm thấy, xếp theo bảng chữ cái
 * @param details      thông tin truy vết: model và bộ luật đã tạo ra kết quả
 */
public record AnalysisResponse(
        UUID id,
        UUID callId,
        Analysis.Status status,
        String errorCode,
        String errorMessage,
        Instant createdAt,
        Instant startedAt,
        Instant completedAt,
        String transcript,
        String language,
        Integer riskScore,
        RiskResult.Level riskLevel,
        BigDecimal confidence,
        List<String> indicators,
        Details details) {

    /**
     * Thông tin truy vết của kết quả.
     *
     * @param modelProbability xác suất lừa đảo do NLP Model tính (0 đến 1)
     */
    public record Details(
            String sttModel,
            BigDecimal modelProbability,
            String nlpModelVersion,
            String rulesetVersion,
            String riskEngineVersion) {
    }

    /** Tạo phản hồi từ lần phân tích, transcript và kết quả rủi ro của nó (hai tham số sau có thể là null). */
    static AnalysisResponse from(Analysis analysis, Transcript transcript, RiskResult risk) {
        Details details = transcript == null && risk == null ? null : new Details(
                transcript == null ? null : transcript.getSttModel(),
                risk == null ? null : risk.getModelProbability(),
                risk == null ? null : risk.getNlpModelVersion(),
                risk == null ? null : risk.getRulesetVersion(),
                risk == null ? null : risk.getRiskEngineVersion());
        return new AnalysisResponse(analysis.getId(), analysis.getCallRecordId(), analysis.getStatus(),
                analysis.getErrorCode(), analysis.getErrorMessage(), analysis.getCreatedAt(),
                analysis.getStartedAt(), analysis.getCompletedAt(),
                transcript == null ? null : transcript.getContent(),
                transcript == null ? null : transcript.getLanguage(),
                risk == null ? null : risk.getRiskScore(),
                risk == null ? null : risk.getRiskLevel(),
                risk == null ? null : risk.getConfidence(),
                risk == null ? null : risk.getIndicators().stream().sorted().toList(),
                details);
    }
}
