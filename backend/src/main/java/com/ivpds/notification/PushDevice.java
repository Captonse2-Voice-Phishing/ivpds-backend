package com.ivpds.notification;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * Một thiết bị nhận thông báo đẩy của người dùng (bảng {@code push_devices}).
 *
 * <p>Dòng được tạo và cập nhật bằng câu lệnh "thêm hoặc cập nhật" trong {@link PushDeviceRepository}, nên lớp này
 * chỉ dùng để đọc.
 */
@Entity
@Table(name = "push_devices")
public class PushDevice {

    /** Hệ điều hành của thiết bị. */
    public enum Platform {
        IOS, ANDROID, WEB
    }

    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    /** Expo push token của một lần cài ứng dụng. */
    @Column(nullable = false, length = 255)
    private String token;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Platform platform;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /** Lần gần nhất ứng dụng đăng ký lại token này. */
    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    /** Constructor rỗng dành cho JPA. */
    protected PushDevice() {
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public String getToken() {
        return token;
    }

    public Platform getPlatform() {
        return platform;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastSeenAt() {
        return lastSeenAt;
    }
}
