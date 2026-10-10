package com.ivpds.notification;

import com.ivpds.common.PageResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** API thông báo của người dùng đang đăng nhập. */
@RestController
@RequestMapping("/api/v1/notifications")
@Tag(name = "Notifications")
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    /** Danh sách thông báo, mới nhất trước. */
    @GetMapping
    @Operation(summary = "List the signed-in user's notifications, newest first")
    public PageResponse<NotificationResponse> list(@AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "false") boolean unreadOnly,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return notificationService.list(userId(jwt), unreadOnly, page, size);
    }

    /** Số thông báo chưa đọc, để hiện huy hiệu trên biểu tượng thông báo. */
    @GetMapping("/unread-count")
    public Map<String, Long> unreadCount(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("unreadCount", notificationService.unreadCount(userId(jwt)));
    }

    /** Đánh dấu một thông báo là đã đọc. */
    @PostMapping("/{id}/read")
    public NotificationResponse markRead(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        return notificationService.markRead(userId(jwt), id);
    }

    /** Đánh dấu đã đọc tất cả thông báo. */
    @PostMapping("/read-all")
    public Map<String, Integer> markAllRead(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("marked", notificationService.markAllRead(userId(jwt)));
    }

    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
