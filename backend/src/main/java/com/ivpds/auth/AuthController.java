package com.ivpds.auth;

import com.ivpds.auth.AuthDtos.AuthResponse;
import com.ivpds.auth.AuthDtos.ChangePasswordRequest;
import com.ivpds.auth.AuthDtos.ForgotPasswordRequest;
import com.ivpds.auth.AuthDtos.LoginRequest;
import com.ivpds.auth.AuthDtos.RefreshTokenRequest;
import com.ivpds.auth.AuthDtos.RegisterRequest;
import com.ivpds.auth.AuthDtos.ResetPasswordRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API xác thực. Các API đánh dấu {@code @SecurityRequirements} (rỗng) là công khai, không cần
 * access token; riêng đổi mật khẩu thì phải đăng nhập.
 */
@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "Auth")
public class AuthController {

    private final AuthService authService;
    private final PasswordResetService passwordResetService;

    public AuthController(AuthService authService, PasswordResetService passwordResetService) {
        this.authService = authService;
        this.passwordResetService = passwordResetService;
    }

    /** Đăng ký tài khoản USER và trả về token để dùng ngay. */
    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    @SecurityRequirements
    @Operation(summary = "Create a USER account and sign in")
    public AuthResponse register(@Valid @RequestBody RegisterRequest request) {
        return authService.register(request);
    }

    /** Đăng nhập bằng email và mật khẩu. */
    @PostMapping("/login")
    @SecurityRequirements
    @Operation(summary = "Sign in with email and password")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request.email(), request.password());
    }

    /** Làm mới token: đổi refresh token lấy cặp token mới, token cũ hết hiệu lực. */
    @PostMapping("/refresh")
    @SecurityRequirements
    @Operation(summary = "Exchange a refresh token for a new token pair (the old refresh token stops working)")
    public AuthResponse refresh(@Valid @RequestBody RefreshTokenRequest request) {
        return authService.refresh(request.refreshToken());
    }

    /** Đăng xuất: thu hồi refresh token. Gọi nhiều lần vẫn trả 204. */
    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @SecurityRequirements
    @Operation(summary = "Revoke a refresh token")
    public void logout(@Valid @RequestBody RefreshTokenRequest request) {
        authService.logout(request.refreshToken());
    }

    /** Đổi mật khẩu của người dùng đang đăng nhập và đăng xuất khỏi mọi thiết bị. */
    @PostMapping("/change-password")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "Change the signed-in user's password and sign out all sessions")
    public void changePassword(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody ChangePasswordRequest request) {
        authService.changePassword(UUID.fromString(jwt.getSubject()), request.currentPassword(),
                request.newPassword());
    }

    /** Quên mật khẩu: gửi mã đặt lại qua email. Luôn trả 204 dù email có đăng ký hay không. */
    @PostMapping("/forgot-password")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @SecurityRequirements
    @Operation(summary = "Email a password reset code (always 204, whether or not the email is registered)")
    public void forgotPassword(@Valid @RequestBody ForgotPasswordRequest request) {
        passwordResetService.requestReset(request.email());
    }

    /** Đặt mật khẩu mới bằng mã đã nhận qua email. */
    @PostMapping("/reset-password")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @SecurityRequirements
    @Operation(summary = "Set a new password using the emailed code")
    public void resetPassword(@Valid @RequestBody ResetPasswordRequest request) {
        passwordResetService.reset(request.email(), request.code(), request.newPassword());
    }
}
