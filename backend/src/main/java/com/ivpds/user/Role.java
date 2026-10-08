package com.ivpds.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Vai trò phân quyền (bảng {@code roles}). Dữ liệu được tạo sẵn bằng migration: USER và ADMIN. */
@Entity
@Table(name = "roles")
public class Role {

    public static final String USER = "USER";
    public static final String ADMIN = "ADMIN";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Short id;

    @Column(nullable = false, length = 30)
    private String name;

    /** Constructor rỗng dành cho JPA. */
    protected Role() {
    }

    public Short getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    /** Hai vai trò bằng nhau khi cùng tên. */
    @Override
    public boolean equals(Object o) {
        return o instanceof Role other && name != null && name.equals(other.name);
    }

    @Override
    public int hashCode() {
        return name == null ? 0 : name.hashCode();
    }
}
