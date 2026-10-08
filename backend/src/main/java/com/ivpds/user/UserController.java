package com.ivpds.user;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** API hồ sơ cá nhân. Người dùng được xác định từ access token, không nhận id từ client. */
@RestController
@RequestMapping("/api/v1/users")
@Tag(name = "Users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /** Xem hồ sơ của người dùng đang đăng nhập. */
    @GetMapping("/me")
    public UserProfileResponse me(@AuthenticationPrincipal Jwt jwt) {
        return userService.getProfile(UUID.fromString(jwt.getSubject()));
    }

    /** Sửa hồ sơ và cài đặt cảnh báo blacklist của người dùng đang đăng nhập. */
    @PatchMapping("/me")
    @Operation(summary = "Update profile fields and the blacklist alert setting; omitted fields are unchanged")
    public UserProfileResponse updateMe(@AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateProfileRequest request) {
        return userService.updateProfile(UUID.fromString(jwt.getSubject()), request);
    }
}
