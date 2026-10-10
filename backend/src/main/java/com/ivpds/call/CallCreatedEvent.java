package com.ivpds.call;

import java.util.UUID;

/**
 * Sự kiện phát ra sau khi một cuộc gọi đã được lưu thành công (gửi file hoặc mở cuộc gọi trực tiếp).
 *
 * @param callId       id của cuộc gọi vừa tạo
 * @param userId       người dùng sở hữu cuộc gọi
 * @param callerNumber số người gọi đã chuẩn hóa, hoặc null nếu không biết
 * @param source       nguồn của cuộc gọi; cuộc gọi LIVE chưa có file audio tại thời điểm này
 */
public record CallCreatedEvent(UUID callId, UUID userId, String callerNumber, CallSource source) {
}
