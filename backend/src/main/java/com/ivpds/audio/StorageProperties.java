package com.ivpds.audio;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Cấu hình kho lưu trữ object tương thích S3 (khóa {@code ivpds.storage} trong application.yml):
 * MinIO khi phát triển, Amazon S3 về sau.
 *
 * @param endpoint        địa chỉ của kho lưu trữ (ví dụ http://minio:9000); để trống khi dùng Amazon S3
 * @param region          vùng (region); MinIO chấp nhận giá trị bất kỳ
 * @param accessKey       khóa truy cập
 * @param secretKey       khóa bí mật
 * @param bucket          bucket chứa file audio của cuộc gọi
 * @param pathStyleAccess dùng URL dạng http://host/bucket/key; MinIO cần bật, Amazon S3 thì không
 * @param connectTimeout  thời gian chờ tối đa khi mở kết nối tới kho lưu trữ
 * @param requestTimeout  thời gian tối đa cho một thao tác, tính cả các lần thử lại. Nếu không giới
 *                        hạn, khi kho lưu trữ ngừng hoạt động request có thể treo nhiều phút rồi vẫn
 *                        thành công sau khi client đã bỏ cuộc từ lâu
 */
@Validated
@ConfigurationProperties("ivpds.storage")
public record StorageProperties(
        URI endpoint,
        @NotBlank String region,
        @NotBlank String accessKey,
        @NotBlank String secretKey,
        @NotBlank String bucket,
        boolean pathStyleAccess,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {
}
