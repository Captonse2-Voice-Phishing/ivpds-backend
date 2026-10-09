package com.ivpds.auth;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code refresh_tokens}. */
interface RefreshTokenRepository extends JpaRepository<RefreshToken, UUID> {

    /** Tìm token theo hash của nó. */
    Optional<RefreshToken> findByTokenHash(String tokenHash);

    // Hai câu lệnh cập nhật hàng loạt dưới đây xóa bộ nhớ đệm của Hibernate (clearAutomatically),
    // nên phải ghi các thay đổi đang chờ xuống database trước (flushAutomatically). Nếu không,
    // thay đổi trong cùng transaction (ví dụ mật khẩu mới vừa đặt) sẽ bị mất.

    /**
     * Thu hồi token nếu nó còn hiệu lực. Trả về 1 nếu chính lần gọi này thu hồi được,
     * 0 nếu token đã bị thu hồi từ trước (dùng để phát hiện hai request dùng chung một token).
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update RefreshToken t set t.revokedAt = :now where t.id = :id and t.revokedAt is null")
    int revokeIfLive(@Param("id") UUID id, @Param("now") Instant now);

    /** Thu hồi mọi token còn hiệu lực của một người dùng; trả về số token bị thu hồi. */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update RefreshToken t set t.revokedAt = :now where t.userId = :userId and t.revokedAt is null")
    int revokeAllForUser(@Param("userId") UUID userId, @Param("now") Instant now);
}
