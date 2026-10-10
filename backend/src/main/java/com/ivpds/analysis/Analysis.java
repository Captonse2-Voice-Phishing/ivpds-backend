package com.ivpds.analysis;

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

/** Một lần phân tích một cuộc gọi (bảng {@code analyses}); một cuộc gọi có thể được phân tích nhiều lần. */
@Entity
@Table(name = "analyses")
public class Analysis {

    /** Trạng thái của một lần phân tích. */
    public enum Status {
        /** Đã nhận yêu cầu, đang chờ tới lượt xử lý. */
        PENDING,
        /** Đang gọi AI service. */
        PROCESSING,
        /** Đã có transcript và kết quả đánh giá rủi ro. */
        COMPLETED,
        /** Không ra được kết quả; xem {@code errorCode}. */
        FAILED
    }

    private static final int MAX_ERROR_CODE_LENGTH = 50;

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "call_record_id", nullable = false, updatable = false)
    private UUID callRecordId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status;

    /** Mã lỗi khi thất bại (ví dụ AI_SERVICE_TIMEOUT, INVALID_AUDIO); null khi chưa thất bại. */
    @Column(name = "error_code", length = MAX_ERROR_CODE_LENGTH)
    private String errorCode;

    /** Thông báo lỗi cho người đọc, không chứa chi tiết nội bộ. */
    @Column(name = "error_message", columnDefinition = "text")
    private String errorMessage;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "completed_at")
    private Instant completedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    /** Constructor rỗng dành cho JPA. */
    protected Analysis() {
    }

    /** Tạo một lần phân tích mới ở trạng thái chờ xử lý. */
    public Analysis(UUID callRecordId) {
        this.callRecordId = callRecordId;
        this.status = Status.PENDING;
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    /** Bắt đầu xử lý. */
    public void start() {
        this.status = Status.PROCESSING;
        this.startedAt = Instant.now();
        this.updatedAt = this.startedAt;
    }

    /** Hoàn tất thành công. */
    public void complete() {
        this.status = Status.COMPLETED;
        this.completedAt = Instant.now();
        this.updatedAt = this.completedAt;
    }

    /** Kết thúc thất bại kèm mã lỗi và thông báo. */
    public void fail(String code, String message) {
        this.status = Status.FAILED;
        this.errorCode = code.length() > MAX_ERROR_CODE_LENGTH ? code.substring(0, MAX_ERROR_CODE_LENGTH) : code;
        this.errorMessage = message;
        this.completedAt = Instant.now();
        this.updatedAt = this.completedAt;
    }

    /** Lần phân tích này đã kết thúc (thành công hoặc thất bại) hay chưa. */
    public boolean isFinished() {
        return status == Status.COMPLETED || status == Status.FAILED;
    }

    public UUID getId() {
        return id;
    }

    public UUID getCallRecordId() {
        return callRecordId;
    }

    public Status getStatus() {
        return status;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public Instant getCompletedAt() {
        return completedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
