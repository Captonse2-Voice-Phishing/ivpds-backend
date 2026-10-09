package com.ivpds.auth;

import com.ivpds.auth.AuthDtos.AuthResponse;
import com.ivpds.auth.AuthDtos.RegisterRequest;
import com.ivpds.auth.AuthDtos.UserSummary;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.user.Emails;
import com.ivpds.user.Role;
import com.ivpds.user.RoleRepository;
import com.ivpds.user.User;
import com.ivpds.user.UserRepository;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Nghiệp vụ xác thực: đăng ký, đăng nhập, làm mới token, đăng xuất và đổi mật khẩu. */
@Service
public class AuthService {

    private final UserRepository users;
    private final RoleRepository roles;
    private final PasswordEncoder passwordEncoder;
    private final AccessTokenService accessTokens;
    private final RefreshTokenService refreshTokens;
    // Hash giả dùng để so sánh khi email không tồn tại, để hai trường hợp đăng nhập thất bại
    // (sai email, sai mật khẩu) đều tốn một lần kiểm tra BCrypt và không phân biệt được qua thời gian.
    private final String dummyPasswordHash;

    public AuthService(UserRepository users, RoleRepository roles, PasswordEncoder passwordEncoder,
            AccessTokenService accessTokens, RefreshTokenService refreshTokens) {
        this.users = users;
        this.roles = roles;
        this.passwordEncoder = passwordEncoder;
        this.accessTokens = accessTokens;
        this.refreshTokens = refreshTokens;
        this.dummyPasswordHash = passwordEncoder.encode(UUID.randomUUID().toString());
    }

    /**
     * Đăng ký tài khoản mới với vai trò USER và đăng nhập luôn.
     * Client không thể tự chọn vai trò; tài khoản ADMIN chỉ được tạo bởi {@link AdminBootstrap}.
     */
    @Transactional
    public AuthResponse register(RegisterRequest request) {
        String email = Emails.normalize(request.email());
        if (users.findByNormalizedEmail(email).isPresent()) {
            throw AuthErrors.emailAlreadyRegistered();
        }
        User user = new User(email, passwordEncoder.encode(request.password()), request.fullName().trim(),
                PhoneNumbers.normalize(request.phoneNumber()));
        user.addRole(roles.findByName(Role.USER)
                .orElseThrow(() -> new IllegalStateException("Role USER is missing from the database")));
        try {
            users.saveAndFlush(user);
        } catch (DataIntegrityViolationException e) {
            // Hai request đăng ký cùng email chạy đồng thời: ràng buộc unique của database quyết định.
            throw AuthErrors.emailAlreadyRegistered();
        }
        return tokensFor(user);
    }

    /**
     * Đăng nhập bằng email và mật khẩu. Sai email và sai mật khẩu trả về cùng một lỗi.
     * Tài khoản bị khóa chỉ được báo là bị khóa khi mật khẩu đã đúng.
     */
    @Transactional
    public AuthResponse login(String email, String password) {
        User user = users.findByNormalizedEmail(Emails.normalize(email)).orElse(null);
        String hash = user != null ? user.getPasswordHash() : dummyPasswordHash;
        if (!passwordEncoder.matches(password, hash) || user == null) {
            throw AuthErrors.invalidCredentials();
        }
        if (!user.isActive()) {
            throw AuthErrors.accountLocked();
        }
        return tokensFor(user);
    }

    /**
     * Đổi refresh token lấy cặp token mới; token cũ không dùng lại được.
     * Cố ý không đặt @Transactional: việc thu hồi token cũ phải được lưu trước khi phát hành cặp mới.
     */
    public AuthResponse refresh(String refreshToken) {
        UUID userId = refreshTokens.consume(refreshToken);
        User user = users.findById(userId).orElseThrow(AuthErrors::invalidRefreshToken);
        if (!user.isActive()) {
            throw AuthErrors.accountLocked();
        }
        return tokensFor(user);
    }

    /** Đăng xuất: thu hồi refresh token được gửi lên. */
    public void logout(String refreshToken) {
        refreshTokens.revoke(refreshToken);
    }

    /**
     * Đổi mật khẩu sau khi kiểm tra mật khẩu hiện tại. Đổi xong thì mọi phiên đăng nhập bị thu hồi;
     * client phải đăng nhập lại bằng mật khẩu mới.
     */
    @Transactional
    public void changePassword(UUID userId, String currentPassword, String newPassword) {
        User user = users.findById(userId).orElseThrow(AuthErrors::invalidCredentials);
        if (!passwordEncoder.matches(currentPassword, user.getPasswordHash())) {
            throw AuthErrors.invalidCurrentPassword();
        }
        user.changePasswordHash(passwordEncoder.encode(newPassword));
        refreshTokens.revokeAllForUser(userId);
    }

    /** Phát hành cặp access token và refresh token cho người dùng. */
    private AuthResponse tokensFor(User user) {
        return new AuthResponse(accessTokens.issue(user), refreshTokens.issue(user.getId()), "Bearer",
                accessTokens.expiresInSeconds(), UserSummary.from(user));
    }
}
