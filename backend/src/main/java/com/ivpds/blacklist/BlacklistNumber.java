package com.ivpds.blacklist;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** Một số điện thoại trong danh sách đen (bảng {@code blacklist_numbers}). */
@Entity
@Table(name = "blacklist_numbers")
public class BlacklistNumber {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** Số điện thoại đã chuẩn hóa; mỗi số chỉ có một dòng. */
    @Column(name = "phone_number", nullable = false, updatable = false, length = 20)
    private String phoneNumber;

    /** Lý do đưa số này vào danh sách, hiển thị cho người tra cứu. */
    @Column(columnDefinition = "text")
    private String reason;

    /** Số đang bị chặn hay đã tạm gỡ; số đã gỡ không còn bị cảnh báo nhưng vẫn giữ lại để xem lịch sử. */
    @Column(nullable = false)
    private boolean active;

    /** Quản trị viên đã thêm số này. */
    @Column(name = "created_by", updatable = false)
    private UUID createdBy;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    /** Constructor rỗng dành cho JPA. */
    protected BlacklistNumber() {
    }

    /** Thêm một số (đã chuẩn hóa) vào danh sách đen ở trạng thái đang chặn. */
    public BlacklistNumber(String phoneNumber, String reason, UUID createdBy) {
        this.phoneNumber = phoneNumber;
        this.reason = reason;
        this.active = true;
        this.createdBy = createdBy;
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    public void changeReason(String reason) {
        this.reason = reason;
        this.updatedAt = Instant.now();
    }

    public void setActive(boolean active) {
        this.active = active;
        this.updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }

    public String getReason() {
        return reason;
    }

    public boolean isActive() {
        return active;
    }

    public UUID getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
