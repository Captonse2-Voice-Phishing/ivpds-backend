package com.ivpds;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * Điểm khởi động của backend IVPDS (kiến trúc Modular Monolith).
 * Mỗi module nghiệp vụ là một package con của {@code com.ivpds} và cùng chạy trong ứng dụng này.
 */
@SpringBootApplication
// Tự động tìm và nạp các lớp cấu hình có @ConfigurationProperties (JwtProperties, StorageProperties, ...).
@ConfigurationPropertiesScan
public class IvpdsApplication {

    /** Khởi động ứng dụng Spring Boot. */
    public static void main(String[] args) {
        SpringApplication.run(IvpdsApplication.class, args);
    }
}
