package com.ivpds.user;

import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Nghiệp vụ hồ sơ cá nhân của người dùng. */
@Service
public class UserService {

    private final UserRepository users;

    public UserService(UserRepository users) {
        this.users = users;
    }

    /** Lấy hồ sơ của người dùng. */
    @Transactional(readOnly = true)
    public UserProfileResponse getProfile(UUID userId) {
        return UserProfileResponse.from(find(userId));
    }

    /**
     * Cập nhật hồ sơ: chỉ thay đổi những trường có gửi lên (họ tên, số điện thoại,
     * bật/tắt cảnh báo blacklist). Thay đổi được lưu khi transaction kết thúc.
     */
    @Transactional
    public UserProfileResponse updateProfile(UUID userId, UpdateProfileRequest request) {
        User user = find(userId);
        if (request.fullName() != null) {
            user.rename(request.fullName().trim());
        }
        if (request.phoneNumber() != null) {
            user.changePhoneNumber(normalizePhone(request.phoneNumber()));
        }
        if (request.blacklistAlertEnabled() != null) {
            user.setBlacklistAlertEnabled(request.blacklistAlertEnabled());
        }
        return UserProfileResponse.from(user);
    }

    /** Tìm người dùng theo id; trả 401 nếu token còn hợp lệ nhưng tài khoản đã bị xóa. */
    private User find(UUID userId) {
        return users.findById(userId).orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED",
                "Authentication is required or the token is invalid."));
    }

    /** Chuẩn hóa số điện thoại; trả 400 nếu không phải số điện thoại hợp lệ. */
    private static String normalizePhone(String phoneNumber) {
        try {
            return PhoneNumbers.normalize(phoneNumber);
        } catch (IllegalArgumentException e) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER",
                    "phoneNumber must contain 6 to 15 digits, optionally starting with +.");
        }
    }
}
