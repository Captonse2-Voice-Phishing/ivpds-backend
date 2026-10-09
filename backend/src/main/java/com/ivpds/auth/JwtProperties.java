package com.ivpds.auth;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình token (khóa {@code ivpds.security.jwt} trong application.yml).
 * Ứng dụng không khởi động được nếu thiếu hoặc sai các giá trị này.
 *
 * @param secret          khóa bí mật để ký access token; HS256 cần ít nhất 256 bit (32 ký tự)
 * @param issuer          tên bên phát hành, được ghi vào token và kiểm tra khi xác thực
 * @param accessTokenTtl  thời hạn của access token
 * @param refreshTokenTtl thời hạn của refresh token
 */
@Validated
@ConfigurationProperties("ivpds.security.jwt")
public record JwtProperties(
        @NotBlank @Size(min = 32, message = "must be at least 32 characters") String secret,
        @NotBlank String issuer,
        @NotNull Duration accessTokenTtl,
        @NotNull Duration refreshTokenTtl) {
}
