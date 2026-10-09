package com.ivpds.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * Một yêu cầu đặt lại mật khẩu (bảng {@code password_reset_tokens}).
 * Chỉ lưu hash của mã đã gửi qua email, không lưu mã gốc.
 */
@Entity
@Table(name = "password_reset_tokens")
public class PasswordResetToken {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    /** Mã 6 chữ số đã băm bằng BCrypt. */
    @Column(name = "code_hash", nullable = false, updatable = false, length = 100)
    private String codeHash;

    @Column(name = "expires_at", nullable = false, updatable = false)
    private Instant expiresAt;

    /** Số lần đã nhập sai mã này. */
    @Column(nullable = false)
    private short attempts;

    /** Thời điểm mã được dùng hoặc bị vô hiệu; {@code null} nghĩa là còn dùng được. */
    @Column(name = "used_at")
    private Instant usedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected PasswordResetToken() {
    }

    PasswordResetToken(UUID userId, String codeHash, Instant createdAt, Instant expiresAt) {
        this.userId = userId;
        this.codeHash = codeHash;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    String getCodeHash() {
        return codeHash;
    }

    Instant getCreatedAt() {
        return createdAt;
    }

    int getAttempts() {
        return attempts;
    }

    /** Mã đã hết hạn tại thời điểm {@code now}. */
    boolean isExpiredAt(Instant now) {
        return !expiresAt.isAfter(now);
    }

    /** Ghi nhận thêm một lần nhập sai. */
    void registerFailedAttempt() {
        attempts++;
    }

    /** Đánh dấu mã đã được dùng, để không dùng lại được nữa. */
    void markUsed(Instant now) {
        usedAt = now;
    }
}
