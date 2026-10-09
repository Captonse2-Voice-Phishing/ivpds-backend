package com.ivpds.user;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * Yêu cầu cập nhật một phần hồ sơ của người dùng đang đăng nhập: trường nào không gửi (null)
 * thì giữ nguyên. Gửi {@code phoneNumber} rỗng nghĩa là xóa số điện thoại đã lưu.
 * Email, vai trò và trạng thái không thể sửa qua API này.
 */
public record UpdateProfileRequest(
        @Size(min = 1, max = 100) @Pattern(regexp = ".*\\S.*", message = "must not be blank") String fullName,
        @Size(max = 30) String phoneNumber,
        Boolean blacklistAlertEnabled) {
}
