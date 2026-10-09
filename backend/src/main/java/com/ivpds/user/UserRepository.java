package com.ivpds.user;

import java.util.Optional;
import java.util.UUID;
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
}
