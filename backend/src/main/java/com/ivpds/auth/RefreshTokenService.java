package com.ivpds.auth;

import com.ivpds.common.error.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Quản lý refresh token. Client giữ chuỗi token ngẫu nhiên, database chỉ giữ hash SHA-256 của nó.
 * Mỗi token chỉ dùng được một lần: khi làm mới, token cũ bị thu hồi và một token mới được phát hành.
 */
@Service
public class RefreshTokenService {

    private static final Logger log = LoggerFactory.getLogger(RefreshTokenService.class);

    private final RefreshTokenRepository tokens;
    private final JwtProperties properties;
    private final SecureRandom random = new SecureRandom();

    public RefreshTokenService(RefreshTokenRepository tokens, JwtProperties properties) {
        this.tokens = tokens;
        this.properties = properties;
    }

    /** Phát hành refresh token mới cho người dùng; trả về token gốc (chỉ xuất hiện duy nhất ở đây). */
    @Transactional
    public String issue(UUID userId) {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String rawToken = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        Instant now = Instant.now();
        tokens.save(new RefreshToken(userId, hash(rawToken), now, now.plus(properties.refreshTokenTtl())));
        return rawToken;
    }

    /**
     * Sử dụng (tiêu thụ) một refresh token và trả về id của người dùng sở hữu nó.
     *
     * <p>Nếu một token đã dùng rồi lại được gửi lên, nghĩa là token đã bị lộ (người dùng thật hoặc
     * kẻ tấn công đang gửi lại nó), nên mọi phiên của người dùng đó bị thu hồi. Việc thu hồi này
     * phải được lưu dù method kết thúc bằng exception, vì vậy dùng {@code noRollbackFor}.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public UUID consume(String rawToken) {
        RefreshToken token = tokens.findByTokenHash(hash(rawToken)).orElseThrow(AuthErrors::invalidRefreshToken);
        Instant now = Instant.now();
        UUID userId = token.getUserId();
        if (token.isRevoked() || tokens.revokeIfLive(token.getId(), now) == 0) {
            int revoked = tokens.revokeAllForUser(userId, now);
            log.warn("Refresh token reuse detected for user {}; revoked {} other session(s)", userId, revoked);
            throw AuthErrors.invalidRefreshToken();
        }
        if (token.isExpiredAt(now)) {
            throw AuthErrors.invalidRefreshToken();
        }
        return userId;
    }

    /** Thu hồi một token (đăng xuất). Token không tồn tại hoặc đã thu hồi thì bỏ qua. */
    @Transactional
    public void revoke(String rawToken) {
        tokens.findByTokenHash(hash(rawToken))
                .ifPresent(token -> tokens.revokeIfLive(token.getId(), Instant.now()));
    }

    /** Thu hồi mọi token của người dùng (đăng xuất khỏi tất cả thiết bị). */
    @Transactional
    public void revokeAllForUser(UUID userId) {
        tokens.revokeAllForUser(userId, Instant.now());
    }

    /** Tính SHA-256 (dạng hex) của token gốc. */
    private static String hash(String rawToken) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(rawToken.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is not available", e);
        }
    }
}
