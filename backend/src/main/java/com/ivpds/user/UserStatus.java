package com.ivpds.user;

/** Trạng thái tài khoản người dùng. */
public enum UserStatus {
    /** Đang hoạt động bình thường. */
    ACTIVE,
    /** Bị khóa: không đăng nhập và không làm mới token được. */
    LOCKED
}
