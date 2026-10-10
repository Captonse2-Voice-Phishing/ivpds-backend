package com.ivpds.audio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Metadata và vị trí lưu trữ của một file audio đã upload (bảng {@code audio_files}).
 * Dữ liệu audio nằm trong kho lưu trữ object, không nằm trong database.
 */
@Entity
@Table(name = "audio_files")
public class AudioFile {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** Cuộc gọi mà file audio này thuộc về; mỗi cuộc gọi có tối đa một file audio. */
    @Column(name = "call_record_id", nullable = false, updatable = false)
    private UUID callRecordId;

    @Column(nullable = false, updatable = false, length = 63)
    private String bucket;

    /** Khóa của object trong bucket, do server sinh ra. */
    @Column(name = "object_key", nullable = false, updatable = false, length = 512)
    private String objectKey;

    /** Tên file gốc của client, chỉ để hiển thị và đặt tên khi tải về. */
    @Column(name = "original_filename")
    private String originalFilename;

    @Column(name = "content_type", nullable = false, length = 100)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    /** Thời lượng tính bằng giây, do AI service (FFmpeg) đo khi phân tích; null nếu chưa phân tích. */
    @Column(name = "duration_seconds", precision = 10, scale = 3)
    private BigDecimal durationSeconds;

    /** SHA-256 (dạng hex) của nội dung file, để kiểm tra tính toàn vẹn. */
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(name = "checksum_sha256", length = 64)
    private String checksumSha256;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected AudioFile() {
    }

    /** Tạo bản ghi metadata cho một file đã được tải lên kho lưu trữ. */
    public AudioFile(UUID callRecordId, String bucket, String objectKey, String originalFilename, String contentType,
            long sizeBytes, String checksumSha256) {
        this.callRecordId = callRecordId;
        this.bucket = bucket;
        this.objectKey = objectKey;
        this.originalFilename = originalFilename;
        this.contentType = contentType;
        this.sizeBytes = sizeBytes;
        this.checksumSha256 = checksumSha256;
        this.createdAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public UUID getCallRecordId() {
        return callRecordId;
    }

    public String getObjectKey() {
        return objectKey;
    }

    public String getOriginalFilename() {
        return originalFilename;
    }

    public String getContentType() {
        return contentType;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }

    public BigDecimal getDurationSeconds() {
        return durationSeconds;
    }

    /** Ghi thời lượng do AI service đo được. */
    public void setDurationSeconds(BigDecimal durationSeconds) {
        this.durationSeconds = durationSeconds;
    }

    public String getChecksumSha256() {
        return checksumSha256;
    }
}
