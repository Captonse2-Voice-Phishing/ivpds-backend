package com.ivpds.auth;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Thông tin tài khoản admin đầu tiên (khóa {@code ivpds.bootstrap.admin}), lấy từ biến môi trường
 * ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_FULL_NAME. Để trống email thì không tạo tài khoản.
 */
@ConfigurationProperties("ivpds.bootstrap.admin")
public record AdminBootstrapProperties(String email, String password, String fullName) {
}
