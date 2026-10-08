package com.ivpds.call;

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

/** Một cuộc gọi mà người dùng gửi lên để phân tích (bảng {@code call_records}). */
@Entity
@Table(name = "call_records")
public class CallRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** Người dùng đã gửi cuộc gọi này. */
    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    /** Số của người gọi đến, đã chuẩn hóa; {@code null} nếu không biết. */
    @Column(name = "caller_number", length = 20)
    private String callerNumber;

    /** Thời điểm cuộc gọi diễn ra (do client cung cấp); khác với thời điểm gửi lên hệ thống. */
    @Column(name = "called_at")
    private Instant calledAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CallSource source;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected CallRecord() {
    }

    /** Tạo bản ghi cuộc gọi mới; số người gọi phải được chuẩn hóa trước khi truyền vào. */
    public CallRecord(UUID userId, String callerNumber, Instant calledAt, CallSource source) {
        this.userId = userId;
        this.callerNumber = callerNumber;
        this.calledAt = calledAt;
        this.source = source;
        this.createdAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public String getCallerNumber() {
        return callerNumber;
    }

    public Instant getCalledAt() {
        return calledAt;
    }

    public CallSource getSource() {
        return source;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
