package com.ivpds.analysis;

import java.util.UUID;

/**
 * Sự kiện phát ra sau khi một lần phân tích hoàn tất và kết quả đã được lưu (cả phân tích file lẫn cuộc gọi trực
 * tiếp). Các module khác (thông báo) nghe sự kiện này; module phân tích không gọi trực tiếp sang họ.
 *
 * @param riskScore điểm rủi ro từ 0 đến 100
 */
public record AnalysisCompletedEvent(UUID analysisId, UUID callId, RiskResult.Level riskLevel, int riskScore) {
}
