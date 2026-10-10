package com.ivpds.notification;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code notifications}. */
public interface NotificationRepository extends JpaRepository<Notification, UUID> {

    /** Thông báo của một người dùng, mới nhất trước. */
    Page<Notification> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);

    /** Chỉ các thông báo chưa đọc của một người dùng, mới nhất trước. */
    Page<Notification> findByUserIdAndReadAtIsNullOrderByCreatedAtDesc(UUID userId, Pageable pageable);

    /** Số thông báo chưa đọc của một người dùng. */
    long countByUserIdAndReadAtIsNull(UUID userId);

    /** Tìm một thông báo, chỉ khi nó thuộc về đúng người dùng đó. */
    Optional<Notification> findByIdAndUserId(UUID id, UUID userId);

    /**
     * Đánh dấu đã đọc mọi thông báo chưa đọc của một người dùng.
     *
     * @return số thông báo vừa được đánh dấu
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update Notification n set n.readAt = :now where n.userId = :userId and n.readAt is null")
    int markAllRead(@Param("userId") UUID userId, @Param("now") Instant now);
}
