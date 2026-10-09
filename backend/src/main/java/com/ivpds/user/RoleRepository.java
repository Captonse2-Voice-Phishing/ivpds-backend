package com.ivpds.user;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** Truy cập dữ liệu bảng {@code roles}. */
public interface RoleRepository extends JpaRepository<Role, Short> {

    /** Tìm vai trò theo tên (USER, ADMIN). */
    Optional<Role> findByName(String name);
}
