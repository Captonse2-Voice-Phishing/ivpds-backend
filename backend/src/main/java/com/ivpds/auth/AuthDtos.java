package com.ivpds.auth;

import com.ivpds.user.User;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

/** Các cấu trúc dữ liệu vào và ra (request, response) của API xác thực. */
public final class AuthDtos {

    // BCrypt chỉ đọc 72 byte đầu của mật khẩu, nên mật khẩu dài hơn bị từ chối thay vì bị cắt ngầm.
    private static final int PASSWORD_MIN = 8;
    private static final int PASSWORD_MAX = 72;

    private AuthDtos() {
    }

    /** Dữ liệu đăng ký tài khoản; số điện thoại là tùy chọn. */
    public record RegisterRequest(
            @NotBlank @Email @Size(max = 255) String email,
            @NotBlank @Size(min = PASSWORD_MIN, max = PASSWORD_MAX) String password,
            @NotBlank @Size(max = 100) String fullName,
            @Pattern(regexp = "^\\+?[0-9]{6,15}$", message = "must contain 6 to 15 digits, optionally starting with +")
            String phoneNumber) {
    }

    /** Dữ liệu đăng nhập. */
    public record LoginRequest(@NotBlank String email, @NotBlank String password) {
    }

    /** Refresh token gửi lên khi làm mới token hoặc đăng xuất. */
    public record RefreshTokenRequest(@NotBlank String refreshToken) {
    }

    /** Dữ liệu đổi mật khẩu: phải nhập đúng mật khẩu hiện tại. */
    public record ChangePasswordRequest(
            @NotBlank String currentPassword,
            @NotBlank @Size(min = PASSWORD_MIN, max = PASSWORD_MAX) String newPassword) {
    }

    /** Email của tài khoản cần đặt lại mật khẩu. */
    public record ForgotPasswordRequest(@NotBlank @Email String email) {
    }

    /** Dữ liệu đặt lại mật khẩu: email, mã 6 chữ số nhận qua email và mật khẩu mới. */
    public record ResetPasswordRequest(
            @NotBlank @Email String email,
            @NotBlank @Pattern(regexp = "\\d{6}", message = "must be 6 digits") String code,
            @NotBlank @Size(min = PASSWORD_MIN, max = PASSWORD_MAX) String newPassword) {
    }

    /**
     * Kết quả đăng ký, đăng nhập hoặc làm mới token.
     *
     * @param expiresIn thời hạn của access token, tính bằng giây
     */
    public record AuthResponse(String accessToken, String refreshToken, String tokenType, long expiresIn,
            UserSummary user) {
    }

    /** Thông tin tóm tắt của người dùng trả về kèm token. */
    public record UserSummary(UUID id, String email, String fullName, List<String> roles) {

        static UserSummary from(User user) {
            return new UserSummary(user.getId(), user.getEmail(), user.getFullName(), user.roleNames());
        }
    }
}
