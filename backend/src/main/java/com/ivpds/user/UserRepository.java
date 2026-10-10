package com.ivpds.user;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code users}. */
public interface UserRepository extends JpaRepository<User, UUID> {

    /**
     * Tìm người dùng theo email đã chuẩn hóa. Email được lưu ở dạng chữ thường, nên phải truyền
     * vào kết quả của {@link Emails#normalize(String)}.
     */
    @Query("select u from User u where lower(u.email) = :email")
    Optional<User> findByNormalizedEmail(@Param("email") String email);

    /** Có tài khoản với id này ở đúng trạng thái đó không; dùng để kiểm tra nhanh mà không tải cả người dùng. */
    boolean existsByIdAndStatus(UUID id, UserStatus status);

    /**
     * Danh sách người dùng cho trang quản trị, mới nhất trước.
     *
     * @param text   chuỗi (chữ thường) cần có trong email hoặc họ tên, hoặc rỗng để không lọc
     * @param status lọc theo trạng thái, hoặc null để lấy tất cả
     */
    @Query("""
            select u from User u
             where (:text = '' or lower(u.email) like concat('%', :text, '%')
                    or lower(u.fullName) like concat('%', :text, '%'))
               and (:status is null or u.status = :status)
             order by u.createdAt desc
            """)
    Page<User> search(@Param("text") String text, @Param("status") UserStatus status, Pageable pageable);
}
