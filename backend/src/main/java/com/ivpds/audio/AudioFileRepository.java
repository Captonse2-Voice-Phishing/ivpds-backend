package com.ivpds.audio;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Truy cập dữ liệu bảng {@code audio_files}. */
public interface AudioFileRepository extends JpaRepository<AudioFile, UUID> {

    /** Tìm file audio của một cuộc gọi. */
    Optional<AudioFile> findByCallRecordId(UUID callRecordId);

    /** Lấy file audio của nhiều cuộc gọi trong một truy vấn, tránh truy vấn lặp cho từng cuộc gọi. */
    List<AudioFile> findByCallRecordIdIn(Collection<UUID> callRecordIds);
}
