package com.ivpds.history;

import com.ivpds.analysis.Analysis;
import com.ivpds.analysis.RiskResult;
import com.ivpds.call.CallSource;
import com.ivpds.history.CallHistoryQueries.Row;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Một cuộc gọi trong lịch sử, kèm kết quả của lần phân tích mới nhất.
 *
 * @param callerBlacklisted số người gọi hiện có nằm trong danh sách đen không
 * @param analysis          lần phân tích mới nhất; null nếu cuộc gọi chưa được phân tích
 * @param owner             chủ cuộc gọi; chỉ có trong API quản trị
 */
public record HistoryResponse(
        UUID callId,
        String callerNumber,
        boolean callerBlacklisted,
        Instant calledAt,
        CallSource source,
        Instant createdAt,
        BigDecimal durationSeconds,
        AnalysisSummary analysis,
        Owner owner) {

    /**
     * Kết quả phân tích. Các trường rủi ro là null khi trạng thái chưa phải COMPLETED; {@code transcript} và
     * {@code details} chỉ có khi xem chi tiết một cuộc gọi.
     */
    public record AnalysisSummary(
            UUID id,
            Analysis.Status status,
            String errorCode,
            String errorMessage,
            Instant completedAt,
            Integer riskScore,
            RiskResult.Level riskLevel,
            BigDecimal confidence,
            List<String> indicators,
            String transcript,
            Details details) {
    }

    /** Thông tin truy vết: model và bộ luật đã tạo ra kết quả. */
    public record Details(String sttModel, BigDecimal modelProbability, String nlpModelVersion,
            String rulesetVersion, String riskEngineVersion) {
    }

    /** Người dùng sở hữu cuộc gọi. */
    public record Owner(UUID id, String email, String fullName) {
    }

    /**
     * @param detailed  kèm transcript và thông tin truy vết
     * @param withOwner kèm chủ cuộc gọi (API quản trị)
     */
    public static HistoryResponse from(Row row, boolean detailed, boolean withOwner) {
        AnalysisSummary analysis = row.analysisId() == null ? null : new AnalysisSummary(row.analysisId(),
                row.status(), row.errorCode(), row.errorMessage(), row.completedAt(), row.riskScore(),
                row.riskLevel(), row.confidence(), row.indicators(), detailed ? row.transcript() : null,
                detailed ? new Details(row.sttModel(), row.modelProbability(), row.nlpModelVersion(),
                        row.rulesetVersion(), row.riskEngineVersion()) : null);
        return new HistoryResponse(row.callId(), row.callerNumber(), row.callerBlacklisted(), row.calledAt(),
                row.source(), row.createdAt(), row.durationSeconds(), analysis,
                withOwner ? new Owner(row.userId(), row.userEmail(), row.userFullName()) : null);
    }
}
