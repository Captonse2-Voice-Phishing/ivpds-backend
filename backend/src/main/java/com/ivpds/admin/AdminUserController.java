package com.ivpds.admin;

import com.ivpds.auth.RefreshTokenService;
import com.ivpds.common.PageResponse;
import com.ivpds.common.error.ApiException;
import com.ivpds.user.User;
import com.ivpds.user.UserRepository;
import com.ivpds.user.UserStatus;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** API quản lý tài khoản người dùng, chỉ dành cho ADMIN: tìm kiếm, xem chi tiết, khóa và mở khóa. */
@RestController
@RequestMapping("/api/v1/admin/users")
@Tag(name = "Admin: users")
public class AdminUserController {

    private static final int MAX_PAGE_SIZE = 100;

    private final UserRepository users;
    private final RefreshTokenService refreshTokens;

    public AdminUserController(UserRepository users, RefreshTokenService refreshTokens) {
        this.users = users;
        this.refreshTokens = refreshTokens;
    }

    /** Tài khoản người dùng trả về cho quản trị viên. Không bao giờ chứa mật khẩu. */
    public record AdminUserResponse(UUID id, String email, String fullName, String phoneNumber, UserStatus status,
            List<String> roles, boolean blacklistAlertEnabled, Instant createdAt) {

        static AdminUserResponse from(User user) {
            return new AdminUserResponse(user.getId(), user.getEmail(), user.getFullName(), user.getPhoneNumber(),
                    user.getStatus(), user.roleNames(), user.isBlacklistAlertEnabled(), user.getCreatedAt());
        }
    }

    /** Yêu cầu đổi trạng thái tài khoản. */
    public record StatusRequest(@NotNull UserStatus status) {
    }

    /** Danh sách tài khoản, mới nhất trước; {@code query} tìm trong email và họ tên. */
    @GetMapping
    @Transactional(readOnly = true)
    @Operation(summary = "Admin: search user accounts, newest first")
    public PageResponse<AdminUserResponse> list(@RequestParam(required = false) String query,
            @RequestParam(required = false) UserStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        String text = query == null ? "" : query.trim().toLowerCase(Locale.ROOT);
        return PageResponse.of(users.search(text, status,
                PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE))), AdminUserResponse::from);
    }

    @GetMapping("/{id}")
    @Transactional(readOnly = true)
    public AdminUserResponse get(@PathVariable UUID id) {
        return AdminUserResponse.from(find(id));
    }

    /**
     * Khóa hoặc mở khóa một tài khoản. Khóa có hiệu lực ngay: access token đang dùng bị từ chối ở request kế tiếp
     * (xem cấu hình bảo mật) và mọi refresh token bị thu hồi. Quản trị viên không tự khóa được chính mình, để hệ
     * thống không rơi vào cảnh không còn ai quản trị.
     */
    @PatchMapping("/{id}/status")
    @Transactional
    @Operation(summary = "Admin: lock or unlock a user account")
    public AdminUserResponse changeStatus(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id,
            @Valid @RequestBody StatusRequest request) {
        User user = find(id);
        if (request.status() == UserStatus.LOCKED && user.getId().toString().equals(jwt.getSubject())) {
            throw new ApiException(HttpStatus.CONFLICT, "CANNOT_LOCK_OWN_ACCOUNT",
                    "An administrator cannot lock their own account.");
        }
        user.changeStatus(request.status());
        AdminUserResponse response = AdminUserResponse.from(user);
        if (request.status() == UserStatus.LOCKED) {
            refreshTokens.revokeAllForUser(user.getId());
        }
        return response;
    }

    private User find(UUID id) {
        return users.findById(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "USER_NOT_FOUND",
                "User not found."));
    }
}
