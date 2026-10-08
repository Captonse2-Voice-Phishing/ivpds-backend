package com.ivpds.auth;

import com.ivpds.user.User;
import java.time.Instant;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;

/** Phát hành access token (JWT) có thời hạn ngắn. */
@Service
public class AccessTokenService {

    private final JwtEncoder encoder;
    private final JwtProperties properties;

    public AccessTokenService(JwtEncoder encoder, JwtProperties properties) {
        this.encoder = encoder;
        this.properties = properties;
    }

    /** Tạo access token cho người dùng: chứa id (subject), danh sách vai trò và thời điểm hết hạn. */
    public String issue(User user) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(properties.issuer())
                .subject(user.getId().toString())
                .issuedAt(now)
                .expiresAt(now.plus(properties.accessTokenTtl()))
                .claim(SecurityConfig.ROLES_CLAIM, user.roleNames())
                .build();
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
        return encoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
    }

    /** Thời hạn của access token tính bằng giây, để client biết khi nào cần làm mới. */
    public long expiresInSeconds() {
        return properties.accessTokenTtl().toSeconds();
    }
}
