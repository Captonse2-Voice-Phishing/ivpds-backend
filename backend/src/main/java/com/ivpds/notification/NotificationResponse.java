package com.ivpds.notification;

import java.time.Instant;
import java.util.UUID;

/**
 * Một thông báo trả về cho người dùng.
 *
 * @param read       đã đọc hay chưa
 * @param analysisId lần phân tích liên quan, nếu có
 * @param callId     cuộc gọi liên quan, nếu có; dùng để mở chi tiết cuộc gọi
 */
public record NotificationResponse(
        UUID id,
        Notification.Type type,
        String title,
        String message,
        boolean read,
        Instant readAt,
        UUID analysisId,
        UUID callId,
        Instant createdAt) {

    static NotificationResponse from(Notification notification) {
        return new NotificationResponse(notification.getId(), notification.getType(), notification.getTitle(),
                notification.getMessage(), notification.getReadAt() != null, notification.getReadAt(),
                notification.getAnalysisId(), notification.getCallId(), notification.getCreatedAt());
    }
}
