package com.ivpds.phishingpattern;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * Một mẫu lừa đảo do quản trị viên ghi nhận (bảng {@code phishing_patterns}): một cụm từ hoặc cách nói đặc trưng
 * của kẻ lừa đảo, gắn với một loại dấu hiệu.
 *
 * <p>Các mẫu đang bật được gửi kèm mỗi yêu cầu phân tích sang AI service, nơi Rule Engine coi mỗi mẫu là một cụm
 * từ cần khớp ở mức nghiêm trọng MEDIUM (xem {@link ActivePhishingPatterns}).
 */
@Entity
@Table(name = "phishing_patterns")
public class PhishingPattern {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 150)
    private String name;

    /** Mã dấu hiệu mà mẫu này thuộc về (ví dụ OTP_REQUEST). */
    @Column(name = "indicator_code", nullable = false, length = 50)
    private String indicatorCode;

    /** Cụm từ hoặc cách nói cần nhận ra. */
    @Column(nullable = false, columnDefinition = "text")
    private String pattern;

    @Column(columnDefinition = "text")
    private String description;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "created_by", updatable = false)
    private UUID createdBy;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    /** Constructor rỗng dành cho JPA. */
    protected PhishingPattern() {
    }

    public PhishingPattern(String name, String indicatorCode, String pattern, String description, UUID createdBy) {
        this.name = name;
        this.indicatorCode = indicatorCode;
        this.pattern = pattern;
        this.description = description;
        this.active = true;
        this.createdBy = createdBy;
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    /** Cập nhật các trường được truyền vào (khác null); {@code description} rỗng nghĩa là xóa mô tả. */
    public void update(String name, String indicatorCode, String pattern, String description, Boolean active) {
        if (name != null) {
            this.name = name;
        }
        if (indicatorCode != null) {
            this.indicatorCode = indicatorCode;
        }
        if (pattern != null) {
            this.pattern = pattern;
        }
        if (description != null) {
            this.description = description.isBlank() ? null : description.trim();
        }
        if (active != null) {
            this.active = active;
        }
        this.updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getIndicatorCode() {
        return indicatorCode;
    }

    public String getPattern() {
        return pattern;
    }

    public String getDescription() {
        return description;
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
