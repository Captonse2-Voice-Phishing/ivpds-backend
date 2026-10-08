package com.ivpds.audio;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3ClientBuilder;

/** Cấu hình client kết nối tới kho lưu trữ object. */
@Configuration
public class StorageConfig {

    /**
     * Tạo client S3 từ cấu hình. Dùng giao thức S3 chuẩn nên cùng một client làm việc được với
     * MinIO lẫn Amazon S3; chuyển đổi giữa hai bên chỉ cần đổi cấu hình, không đổi code.
     */
    @Bean
    S3Client s3Client(StorageProperties properties) {
        S3ClientBuilder builder = S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(properties.accessKey(), properties.secretKey())))
                .forcePathStyle(properties.pathStyleAccess())
                .httpClientBuilder(ApacheHttpClient.builder().connectionTimeout(properties.connectTimeout()))
                .overrideConfiguration(c -> c.apiCallTimeout(properties.requestTimeout()));
        if (properties.endpoint() != null) {
            builder.endpointOverride(properties.endpoint());
        }
        return builder.build();
    }
}
