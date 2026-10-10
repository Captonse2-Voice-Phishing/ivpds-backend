package com.ivpds.notification;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

/** Truy cập dữ liệu bảng {@code push_devices}. */
public interface PushDeviceRepository extends JpaRepository<PushDevice, UUID> {

    /** Các thiết bị của một người dùng, thiết bị dùng gần đây nhất trước. */
    List<PushDevice> findByUserIdOrderByLastSeenAtDesc(UUID userId);

    /**
     * Đăng ký một token cho người dùng. Token đã có thì được chuyển sang người dùng này (người vừa đăng nhập trên
     * thiết bị đó) và ghi lại thời điểm; chạy trong một câu lệnh nên hai lần đăng ký đồng thời không xung đột.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query(value = """
            insert into push_devices (user_id, token, platform) values (:userId, :token, :platform)
            on conflict (token) do update
               set user_id = excluded.user_id, platform = excluded.platform, last_seen_at = now()
            """, nativeQuery = true)
    void register(@Param("userId") UUID userId, @Param("token") String token, @Param("platform") String platform);

    /** Gỡ một token của đúng người dùng đó; trả về số dòng đã xóa. */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from PushDevice d where d.userId = :userId and d.token = :token")
    int deleteByUserIdAndToken(@Param("userId") UUID userId, @Param("token") String token);

    /** Xóa các token mà dịch vụ đẩy báo là không còn dùng được. */
    @Transactional
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from PushDevice d where d.token in :tokens")
    int deleteByTokenIn(@Param("tokens") Collection<String> tokens);
}
