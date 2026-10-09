package com.ivpds.call;

import com.ivpds.audio.AudioFile;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * Thông tin một cuộc gọi trả về cho chủ sở hữu.
 * Chi tiết lưu trữ (bucket, khóa object) không bao giờ được đưa ra ngoài.
 */
public record CallResponse(
        UUID id,
        String callerNumber,
        Instant calledAt,
        CallSource source,
        Instant createdAt,
        Audio audio) {

    /** Metadata của file audio thuộc cuộc gọi. */
    public record Audio(
            UUID id,
            String originalFilename,
            String contentType,
            long sizeBytes,
            BigDecimal durationSeconds,
            String checksumSha256) {
    }

    /** Tạo phản hồi từ entity cuộc gọi và file audio của nó ({@code audio} có thể là null). */
    static CallResponse from(CallRecord call, AudioFile audio) {
        Audio audioPart = audio == null ? null : new Audio(audio.getId(), audio.getOriginalFilename(),
                audio.getContentType(), audio.getSizeBytes(), audio.getDurationSeconds(), audio.getChecksumSha256());
        return new CallResponse(call.getId(), call.getCallerNumber(), call.getCalledAt(), call.getSource(),
                call.getCreatedAt(), audioPart);
    }
}
