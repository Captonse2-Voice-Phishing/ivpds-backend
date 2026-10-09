package com.ivpds.auth;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình chức năng quên mật khẩu (khóa {@code ivpds.security.password-reset}).
 *
 * @param codeTtl        thời hạn hiệu lực của mã đặt lại mật khẩu
 * @param maxAttempts    số lần nhập sai tối đa trước khi mã bị vô hiệu
 * @param resendInterval khoảng cách tối thiểu giữa hai lần gửi mã cho cùng một tài khoản
 */
@Validated
@ConfigurationProperties("ivpds.security.password-reset")
public record PasswordResetProperties(
        @NotNull Duration codeTtl,
        @Min(1) int maxAttempts,
        @NotNull Duration resendInterval) {
}
