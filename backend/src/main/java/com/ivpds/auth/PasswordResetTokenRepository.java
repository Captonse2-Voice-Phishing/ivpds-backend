package com.ivpds.auth;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code password_reset_tokens}. */
interface PasswordResetTokenRepository extends JpaRepository<PasswordResetToken, UUID> {

    /** Yêu cầu đặt lại gần nhất của người dùng (kể cả đã dùng), để giới hạn tần suất gửi email. */
    Optional<PasswordResetToken> findFirstByUserIdOrderByCreatedAtDesc(UUID userId);

    /** Mã chưa dùng gần nhất của người dùng, là mã duy nhất còn có thể dùng để đặt lại mật khẩu. */
    Optional<PasswordResetToken> findFirstByUserIdAndUsedAtIsNullOrderByCreatedAtDesc(UUID userId);

    /** Vô hiệu mọi mã chưa dùng của người dùng, trước khi phát hành mã mới. */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update PasswordResetToken t set t.usedAt = :now where t.userId = :userId and t.usedAt is null")
    int invalidateAllForUser(@Param("userId") UUID userId, @Param("now") Instant now);
}
