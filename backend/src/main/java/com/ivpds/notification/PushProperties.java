package com.ivpds.notification;

import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình gửi thông báo đẩy qua Expo Push Service (khóa {@code ivpds.push} trong application.yml).
 *
 * @param enabled        có gửi thông báo đẩy không; mặc định tắt, vì bật lên là gửi tiêu đề và nội dung thông báo
 *                       ra dịch vụ bên ngoài (Expo, rồi tới Apple/Google)
 * @param url            địa chỉ API gửi của Expo
 * @param accessToken    access token của tài khoản Expo, chỉ cần khi dự án Expo bật "enhanced push security";
 *                       rỗng thì không gửi header {@code Authorization}
 * @param connectTimeout thời gian chờ tối đa khi mở kết nối
 * @param requestTimeout thời gian chờ tối đa cho một lần gửi
 */
@Validated
@ConfigurationProperties("ivpds.push")
public record PushProperties(
        boolean enabled,
        @NotNull URI url,
        String accessToken,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {
}
