package com.ivpds.blacklist;

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

/**
 * Một báo cáo của người dùng về một số điện thoại lừa đảo (bảng {@code blacklist_reports}).
 *
 * <p>Báo cáo không tự đưa số vào danh sách đen: quản trị viên phải duyệt trước, để một người dùng không thể tự ý
 * chặn số của người khác.
 */
@Entity
@Table(name = "blacklist_reports")
public class BlacklistReport {

    /** Trạng thái xử lý của một báo cáo. */
    public enum Status {
        /** Đang chờ quản trị viên xem. */
        PENDING,
        /** Đã duyệt: số đã được đưa vào danh sách đen. */
        APPROVED,
        /** Bị từ chối: số không được đưa vào danh sách đen vì báo cáo này. */
        REJECTED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** Số bị báo cáo, đã chuẩn hóa. */
    @Column(name = "phone_number", nullable = false, updatable = false, length = 20)
    private String phoneNumber;

    @Column(name = "reporter_id", nullable = false, updatable = false)
    private UUID reporterId;

    /** Cuộc gọi mà người dùng báo cáo từ đó, nếu có; quản trị viên xem cuộc gọi này để quyết định. */
    @Column(name = "call_record_id", updatable = false)
    private UUID callId;

    @Column(updatable = false, columnDefinition = "text")
    private String reason;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status;

    /** Quản trị viên đã duyệt hoặc từ chối; null khi còn chờ. */
    @Column(name = "reviewed_by")
    private UUID reviewedBy;

    @Column(name = "reviewed_at")
    private Instant reviewedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected BlacklistReport() {
    }

    /** Tạo một báo cáo ở trạng thái chờ duyệt; {@code phoneNumber} phải là số đã chuẩn hóa. */
    public BlacklistReport(String phoneNumber, UUID reporterId, UUID callId, String reason) {
        this.phoneNumber = phoneNumber;
        this.reporterId = reporterId;
        this.callId = callId;
        this.reason = reason;
        this.status = Status.PENDING;
        this.createdAt = Instant.now();
    }

    /** Ghi lại quyết định của quản trị viên. */
    public void review(Status decision, UUID adminId, Instant at) {
        this.status = decision;
        this.reviewedBy = adminId;
        this.reviewedAt = at;
    }

    public UUID getId() {
        return id;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }

    public UUID getReporterId() {
        return reporterId;
    }

    public UUID getCallId() {
        return callId;
    }

    public String getReason() {
        return reason;
    }

    public Status getStatus() {
        return status;
    }

    public UUID getReviewedBy() {
        return reviewedBy;
    }

    public Instant getReviewedAt() {
        return reviewedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
