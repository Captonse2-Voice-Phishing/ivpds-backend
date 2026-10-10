package com.ivpds.auth;

import com.ivpds.user.UserRepository;
import com.ivpds.user.UserStatus;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

/** Cấu hình bảo mật: quy tắc truy cập từng nhóm API, xác thực bằng JWT và băm mật khẩu. */
@Configuration
public class SecurityConfig {

    /** Tên claim trong access token chứa danh sách vai trò. */
    static final String ROLES_CLAIM = "roles";

    /** Các API xác thực không cần đăng nhập. */
    private static final String[] PUBLIC_AUTH_ENDPOINTS = {
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
    };

    /** Health check và tài liệu API, không cần đăng nhập. */
    private static final String[] PUBLIC_INFRA_ENDPOINTS = {
            "/actuator/health",
            "/actuator/health/**",
            "/v3/api-docs",
            "/v3/api-docs/**",
            "/swagger-ui.html",
            "/swagger-ui/**",
    };

    /**
     * Luồng WebSocket của cuộc gọi trực tiếp. Không dùng Bearer token ở đây: client lấy một vé dùng một lần qua
     * {@code POST /api/v1/live-calls} (API đó cần đăng nhập) và backend kiểm tra vé khi bắt tay WebSocket.
     */
    private static final String LIVE_CALL_STREAM = "/api/v1/live-calls/stream";

    /**
     * Quy tắc truy cập: nhóm công khai ai cũng gọi được, {@code /api/v1/admin/**} chỉ dành cho ADMIN,
     * mọi API còn lại phải đăng nhập bằng token của một tài khoản đang hoạt động. Lỗi 401 và 403 do
     * {@link SecurityErrorHandler} trả về.
     */
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, SecurityErrorHandler errors, UserRepository users)
            throws Exception {
        http
                // API dùng Bearer token, không dùng cookie hay session phía server, nên không cần chống CSRF.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(PUBLIC_AUTH_ENDPOINTS).permitAll()
                        .requestMatchers(PUBLIC_INFRA_ENDPOINTS).permitAll()
                        .requestMatchers(LIVE_CALL_STREAM).permitAll()
                        .requestMatchers("/api/v1/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(activeAccountsOnly(users)))
                        .authenticationEntryPoint(errors)
                        .accessDeniedHandler(errors))
                .exceptionHandling(e -> e.authenticationEntryPoint(errors).accessDeniedHandler(errors));
        return http.build();
    }

    /** Bộ băm mật khẩu BCrypt, dùng cho mật khẩu người dùng và mã đặt lại mật khẩu. */
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /** Bộ ký access token bằng khóa bí mật (HS256). */
    @Bean
    JwtEncoder jwtEncoder(JwtProperties properties) {
        return new NimbusJwtEncoder(new ImmutableSecret<>(secretKey(properties)));
    }

    /** Bộ kiểm tra access token: đúng chữ ký, chưa hết hạn và đúng bên phát hành (issuer). */
    @Bean
    JwtDecoder jwtDecoder(JwtProperties properties) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withSecretKey(secretKey(properties))
                .macAlgorithm(MacAlgorithm.HS256)
                .build();
        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(properties.issuer()));
        return decoder;
    }

    /**
     * Chấp nhận access token chỉ khi tài khoản của nó còn tồn tại và đang hoạt động. Access token tự nó không thu
     * hồi được, nên nếu chỉ tin vào chữ ký thì một tài khoản vừa bị khóa vẫn dùng tiếp được tới khi token hết hạn.
     * Đổi lại là một truy vấn nhỏ vào database cho mỗi request có đăng nhập.
     */
    private static Converter<Jwt, AbstractAuthenticationToken> activeAccountsOnly(UserRepository users) {
        JwtAuthenticationConverter converter = jwtAuthenticationConverter();
        return jwt -> {
            UUID userId;
            try {
                userId = UUID.fromString(jwt.getSubject());
            } catch (RuntimeException e) {
                throw new BadCredentialsException("The token has no valid subject.");
            }
            if (!users.existsByIdAndStatus(userId, UserStatus.ACTIVE)) {
                throw new DisabledException("The account is locked or no longer exists.");
            }
            return converter.convert(jwt);
        };
    }

    /** Chuyển claim {@code roles} trong token thành quyền của Spring Security (USER thành ROLE_USER). */
    private static JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter authorities = new JwtGrantedAuthoritiesConverter();
        authorities.setAuthoritiesClaimName(ROLES_CLAIM);
        authorities.setAuthorityPrefix("ROLE_");
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }

    /** Tạo khóa HMAC từ chuỗi bí mật trong cấu hình. */
    private static SecretKey secretKey(JwtProperties properties) {
        return new SecretKeySpec(properties.secret().getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }
}
