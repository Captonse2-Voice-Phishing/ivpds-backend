package com.ivpds.auth;

import com.ivpds.common.error.ApiException;
import org.springframework.http.HttpStatus;

/** Nơi tập trung các lỗi của module xác thực, để mã lỗi và thông báo thống nhất ở mọi chỗ. */
final class AuthErrors {

    private AuthErrors() {
    }

    /** Sai email hoặc mật khẩu. Dùng chung cho cả hai trường hợp để không lộ email nào đã đăng ký. */
    static ApiException invalidCredentials() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "Email or password is incorrect.");
    }

    /** Tài khoản đang bị khóa. */
    static ApiException accountLocked() {
        return new ApiException(HttpStatus.FORBIDDEN, "ACCOUNT_LOCKED", "This account is locked.");
    }

    /** Email đã được dùng để đăng ký. */
    static ApiException emailAlreadyRegistered() {
        return new ApiException(HttpStatus.CONFLICT, "EMAIL_ALREADY_REGISTERED", "This email is already registered.");
    }

    /** Refresh token không tồn tại, đã hết hạn hoặc đã bị thu hồi. */
    static ApiException invalidRefreshToken() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_REFRESH_TOKEN",
                "Refresh token is invalid, expired or revoked.");
    }

    /** Mật khẩu hiện tại nhập sai khi đổi mật khẩu. */
    static ApiException invalidCurrentPassword() {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_CURRENT_PASSWORD", "Current password is incorrect.");
    }

    /** Mã đặt lại mật khẩu sai, hết hạn, đã dùng hoặc đã nhập sai quá số lần cho phép. */
    static ApiException invalidResetCode() {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_RESET_CODE", "Reset code is invalid or expired.");
    }
}
