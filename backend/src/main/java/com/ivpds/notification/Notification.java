package com.ivpds.notification;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** Một thông báo gửi cho người dùng (bảng {@code notifications}). */
@Entity
@Table(name = "notifications")
public class Notification {

    /** Loại thông báo; ứng dụng dùng giá trị này để chọn biểu tượng và màn hình mở ra khi bấm vào. */
    public enum Type {
        /** Cuộc gọi vừa phân tích có mức rủi ro HIGH. */
        HIGH_RISK_CALL,
        /** Cuộc gọi vừa phân tích có mức rủi ro MEDIUM. */
        SUSPICIOUS_CALL,
        /** Số người gọi nằm trong danh sách đen. */
        BLACKLISTED_CALLER
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, updatable = false, length = 30)
    private Type type;

    @Column(nullable = false, updatable = false, length = 200)
    private String title;

    @Column(nullable = false, updatable = false, columnDefinition = "text")
    private String message;

    /** Lần phân tích liên quan, nếu có. */
    @Column(name = "analysis_id", updatable = false)
    private UUID analysisId;

    /** Cuộc gọi liên quan, để ứng dụng mở đúng cuộc gọi khi người dùng bấm vào thông báo. */
    @Column(name = "call_record_id", updatable = false)
    private UUID callId;

    /** Thời điểm người dùng đọc thông báo; null nếu chưa đọc. */
    @Column(name = "read_at")
    private Instant readAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected Notification() {
    }

    public Notification(UUID userId, Type type, String title, String message, UUID analysisId, UUID callId) {
        this.userId = userId;
        this.type = type;
        this.title = title;
        this.message = message;
        this.analysisId = analysisId;
        this.callId = callId;
        this.createdAt = Instant.now();
    }

    /** Đánh dấu đã đọc; đọc lại không đổi thời điểm đọc đầu tiên. */
    public void markRead() {
        if (readAt == null) {
            readAt = Instant.now();
        }
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public Type getType() {
        return type;
    }

    public String getTitle() {
        return title;
    }

    public String getMessage() {
        return message;
    }

    public UUID getAnalysisId() {
        return analysisId;
    }

    public UUID getCallId() {
        return callId;
    }

    public Instant getReadAt() {
        return readAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
