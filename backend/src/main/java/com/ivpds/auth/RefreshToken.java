package com.ivpds.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** Một refresh token đã phát hành (bảng {@code refresh_tokens}). Chỉ lưu hash, không lưu token gốc. */
@Entity
@Table(name = "refresh_tokens")
public class RefreshToken {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    /** SHA-256 (dạng hex, 64 ký tự) của token gốc. */
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(name = "token_hash", nullable = false, updatable = false, length = 64)
    private String tokenHash;

    @Column(name = "expires_at", nullable = false, updatable = false)
    private Instant expiresAt;

    /** Thời điểm bị thu hồi; {@code null} nghĩa là token còn dùng được. */
    @Column(name = "revoked_at")
    private Instant revokedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected RefreshToken() {
    }

    RefreshToken(UUID userId, String tokenHash, Instant createdAt, Instant expiresAt) {
        this.userId = userId;
        this.tokenHash = tokenHash;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    UUID getId() {
        return id;
    }

    UUID getUserId() {
        return userId;
    }

    /** Token đã bị thu hồi (đã dùng để làm mới, đã đăng xuất, hoặc bị thu hồi hàng loạt). */
    boolean isRevoked() {
        return revokedAt != null;
    }

    /** Token đã hết hạn tại thời điểm {@code now}. */
    boolean isExpiredAt(Instant now) {
        return !expiresAt.isAfter(now);
    }
}
