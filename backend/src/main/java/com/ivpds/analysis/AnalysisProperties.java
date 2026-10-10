package com.ivpds.analysis;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình việc phân tích cuộc gọi (khóa {@code ivpds.analysis} trong application.yml).
 *
 * @param autoStart     tự bắt đầu phân tích ngay khi người dùng gửi một cuộc gọi
 * @param workers       số lần phân tích chạy cùng lúc; AI service chạy trên CPU nên giữ con số này nhỏ
 * @param queueCapacity số lần phân tích được phép xếp hàng chờ; vượt quá thì yêu cầu mới bị từ chối
 */
@Validated
@ConfigurationProperties("ivpds.analysis")
public record AnalysisProperties(
        boolean autoStart,
        @Min(1) @Max(16) int workers,
        @Min(1) @Max(10_000) int queueCapacity) {
}
