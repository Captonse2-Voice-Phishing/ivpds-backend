package com.ivpds.notification;

import java.util.UUID;

/**
 * Phát ra khi một thông báo vừa được lưu, để kênh đẩy gửi nó tới thiết bị của người dùng.
 *
 * @param notificationId id của thông báo
 * @param userId         người nhận
 * @param type           loại thông báo
 * @param title          tiêu đề hiển thị
 * @param message        nội dung hiển thị
 * @param analysisId     lần phân tích liên quan, có thể null
 * @param callId         cuộc gọi liên quan, có thể null
 */
public record NotificationCreatedEvent(UUID notificationId, UUID userId, Notification.Type type, String title,
        String message, UUID analysisId, UUID callId) {

    static NotificationCreatedEvent of(Notification n) {
        return new NotificationCreatedEvent(n.getId(), n.getUserId(), n.getType(), n.getTitle(), n.getMessage(),
                n.getAnalysisId(), n.getCallId());
    }
}
