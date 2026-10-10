package com.ivpds.notification;

import com.ivpds.analysis.AnalysisCompletedEvent;
import com.ivpds.analysis.RiskResult;
import com.ivpds.call.CallRecordRepository;
import com.ivpds.common.PageResponse;
import com.ivpds.common.error.ApiException;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Nghiệp vụ thông báo: tạo thông báo khi có sự kiện đáng báo, và cho người dùng xem, đếm, đánh dấu đã đọc.
 *
 * <p>Thông báo được lưu trong database và ứng dụng lấy về qua API. Mỗi thông báo vừa lưu còn được phát ra dưới
 * dạng {@link NotificationCreatedEvent} để {@link PushSender} đẩy tới thiết bị của người dùng (nếu kênh đẩy bật).
 * Tiêu đề và nội dung viết bằng tiếng Việt vì đó là chữ hiển thị thẳng cho người dùng cuối.
 */
@Service
public class NotificationService {

    private static final Logger log = LoggerFactory.getLogger(NotificationService.class);
    private static final int MAX_PAGE_SIZE = 100;

    private final NotificationRepository notifications;
    private final CallRecordRepository calls;
    private final ApplicationEventPublisher events;

    public NotificationService(NotificationRepository notifications, CallRecordRepository calls,
            ApplicationEventPublisher events) {
        this.events = events;
        this.notifications = notifications;
        this.calls = calls;
    }

    /** Tạo một thông báo cho người dùng. */
    @Transactional
    public Notification create(UUID userId, Notification.Type type, String title, String message, UUID analysisId,
            UUID callId) {
        Notification saved = notifications.save(new Notification(userId, type, title, message, analysisId, callId));
        events.publishEvent(NotificationCreatedEvent.of(saved));
        return saved;
    }

    /**
     * Khi một lần phân tích hoàn tất với mức MEDIUM hoặc HIGH, báo cho chủ cuộc gọi. Mức LOW không tạo thông báo.
     * Lỗi ở đây chỉ được ghi log: việc không tạo được thông báo không được làm hỏng kết quả phân tích.
     */
    @EventListener
    public void onAnalysisCompleted(AnalysisCompletedEvent event) {
        if (event.riskLevel() == RiskResult.Level.LOW) {
            return;
        }
        try {
            calls.findById(event.callId()).ifPresent(call -> {
                boolean high = event.riskLevel() == RiskResult.Level.HIGH;
                String caller = call.getCallerNumber() == null ? "" : " từ số " + call.getCallerNumber();
                Notification saved = notifications.save(new Notification(call.getUserId(),
                        high ? Notification.Type.HIGH_RISK_CALL : Notification.Type.SUSPICIOUS_CALL,
                        high ? "Cuộc gọi có nguy cơ lừa đảo cao" : "Cuộc gọi có dấu hiệu đáng ngờ",
                        "Cuộc gọi%s được đánh giá mức %s với %d/100 điểm rủi ro.%s".formatted(caller,
                                high ? "nguy cơ cao" : "đáng ngờ", event.riskScore(),
                                high ? " Không cung cấp mã OTP, mật khẩu hay chuyển tiền theo yêu cầu của người gọi."
                                        : " Hãy kiểm tra lại thông tin trước khi làm theo yêu cầu của người gọi."),
                        event.analysisId(), event.callId()));
                events.publishEvent(NotificationCreatedEvent.of(saved));
            });
        } catch (RuntimeException e) {
            log.error("Could not create a notification for analysis {}", event.analysisId(), e);
        }
    }

    /** Thông báo của người dùng, mới nhất trước; {@code unreadOnly} để chỉ lấy thông báo chưa đọc. */
    @Transactional(readOnly = true)
    public PageResponse<NotificationResponse> list(UUID userId, boolean unreadOnly, int page, int size) {
        Pageable pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        Page<Notification> result = unreadOnly
                ? notifications.findByUserIdAndReadAtIsNullOrderByCreatedAtDesc(userId, pageable)
                : notifications.findByUserIdOrderByCreatedAtDesc(userId, pageable);
        return PageResponse.of(result, NotificationResponse::from);
    }

    /** Số thông báo chưa đọc. */
    @Transactional(readOnly = true)
    public long unreadCount(UUID userId) {
        return notifications.countByUserIdAndReadAtIsNull(userId);
    }

    /** Đánh dấu một thông báo của chính người dùng là đã đọc. */
    @Transactional
    public NotificationResponse markRead(UUID userId, UUID notificationId) {
        Notification notification = notifications.findByIdAndUserId(notificationId, userId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "NOTIFICATION_NOT_FOUND",
                        "Notification not found."));
        notification.markRead();
        return NotificationResponse.from(notification);
    }

    /** Đánh dấu đã đọc mọi thông báo của người dùng; trả về số thông báo vừa được đánh dấu. */
    @Transactional
    public int markAllRead(UUID userId) {
        return notifications.markAllRead(userId, Instant.now());
    }
}
