package com.ivpds.user;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Thông tin hồ sơ trả về cho chính người dùng đó. Không bao giờ chứa mật khẩu. */
public record UserProfileResponse(
        UUID id,
        String email,
        String fullName,
        String phoneNumber,
        UserStatus status,
        boolean blacklistAlertEnabled,
        List<String> roles,
        Instant createdAt) {

    /** Tạo phản hồi từ entity người dùng. */
    static UserProfileResponse from(User user) {
        return new UserProfileResponse(user.getId(), user.getEmail(), user.getFullName(), user.getPhoneNumber(),
                user.getStatus(), user.isBlacklistAlertEnabled(), user.roleNames(), user.getCreatedAt());
    }
}
