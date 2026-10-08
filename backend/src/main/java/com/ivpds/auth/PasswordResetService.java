package com.ivpds.auth;

import com.ivpds.common.error.ApiException;
import com.ivpds.user.Emails;
import com.ivpds.user.User;
import com.ivpds.user.UserRepository;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Optional;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Chức năng quên mật khẩu: gửi qua email một mã 6 chữ số có thời hạn ngắn,
 * rồi cho phép người dùng đặt mật khẩu mới bằng mã đó.
 */
@Service
public class PasswordResetService {

    private final UserRepository users;
    private final PasswordResetTokenRepository tokens;
    private final PasswordEncoder passwordEncoder;
    private final PasswordResetMailer mailer;
    private final RefreshTokenService refreshTokens;
    private final PasswordResetProperties properties;
    private final SecureRandom random = new SecureRandom();

    public PasswordResetService(UserRepository users, PasswordResetTokenRepository tokens,
            PasswordEncoder passwordEncoder, PasswordResetMailer mailer, RefreshTokenService refreshTokens,
            PasswordResetProperties properties) {
        this.users = users;
        this.tokens = tokens;
        this.passwordEncoder = passwordEncoder;
        this.mailer = mailer;
        this.refreshTokens = refreshTokens;
        this.properties = properties;
    }

    /**
     * Xử lý yêu cầu quên mật khẩu: tạo mã mới, vô hiệu các mã cũ và gửi email.
     *
     * <p>Method này không bao giờ cho biết email có thuộc về tài khoản nào hay không, để người gọi
     * không dò được email đã đăng ký. Mỗi tài khoản chỉ được gửi một email trong mỗi khoảng
     * {@code resendInterval}, tránh bị lợi dụng để gửi thư hàng loạt.
     */
    @Transactional
    public void requestReset(String email) {
        Optional<User> found = users.findByNormalizedEmail(Emails.normalize(email)).filter(User::isActive);
        if (found.isEmpty()) {
            return;
        }
        User user = found.get();
        Instant now = Instant.now();
        boolean requestedRecently = tokens.findFirstByUserIdOrderByCreatedAtDesc(user.getId())
                .map(last -> last.getCreatedAt().plus(properties.resendInterval()).isAfter(now))
                .orElse(false);
        if (requestedRecently) {
            return;
        }
        tokens.invalidateAllForUser(user.getId(), now);
        String code = "%06d".formatted(random.nextInt(1_000_000));
        tokens.save(new PasswordResetToken(user.getId(), passwordEncoder.encode(code), now,
                now.plus(properties.codeTtl())));
        mailer.send(user.getEmail(), code, properties.codeTtl());
    }

    /**
     * Đặt mật khẩu mới bằng mã trong email. Mã chỉ dùng được một lần, có thời hạn và bị khóa sau
     * khi nhập sai quá số lần cho phép. Đặt lại thành công thì mọi phiên đăng nhập bị thu hồi.
     *
     * <p>Số lần nhập sai phải được lưu dù method kết thúc bằng exception, vì vậy dùng
     * {@code noRollbackFor}.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public void reset(String email, String code, String newPassword) {
        User user = users.findByNormalizedEmail(Emails.normalize(email))
                .filter(User::isActive)
                .orElseThrow(AuthErrors::invalidResetCode);
        PasswordResetToken token = tokens.findFirstByUserIdAndUsedAtIsNullOrderByCreatedAtDesc(user.getId())
                .orElseThrow(AuthErrors::invalidResetCode);
        Instant now = Instant.now();
        if (token.isExpiredAt(now) || token.getAttempts() >= properties.maxAttempts()) {
            throw AuthErrors.invalidResetCode();
        }
        if (!passwordEncoder.matches(code, token.getCodeHash())) {
            token.registerFailedAttempt();
            throw AuthErrors.invalidResetCode();
        }
        token.markUsed(now);
        user.changePasswordHash(passwordEncoder.encode(newPassword));
        refreshTokens.revokeAllForUser(user.getId());
    }
}
