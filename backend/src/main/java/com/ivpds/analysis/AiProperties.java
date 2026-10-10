package com.ivpds.analysis;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình kết nối tới AI service (khóa {@code ivpds.ai} trong application.yml).
 *
 * @param baseUrl              địa chỉ gốc của AI service (ví dụ http://ai:8000)
 * @param apiKey               khóa API gửi trong header {@code X-API-Key}
 * @param connectTimeout       thời gian chờ tối đa khi mở kết nối
 * @param transcriptionTimeout thời gian chờ tối đa cho một lần nhận dạng giọng nói; phải dài vì Whisper
 *                             chạy trên CPU có thể mất nhiều phút với cuộc gọi dài
 * @param riskTimeout          thời gian chờ tối đa cho một lần đánh giá rủi ro trên transcript
 * @param liveFinishTimeout    sau khi cuộc gọi trực tiếp kết thúc, chờ AI service trả kết quả cuối tối đa bao lâu
 */
@Validated
@ConfigurationProperties("ivpds.ai")
public record AiProperties(
        @NotNull URI baseUrl,
        @NotBlank String apiKey,
        @NotNull Duration connectTimeout,
        @NotNull Duration transcriptionTimeout,
        @NotNull Duration riskTimeout,
        @NotNull Duration liveFinishTimeout) {
}
