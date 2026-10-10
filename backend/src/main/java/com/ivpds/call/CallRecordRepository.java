package com.ivpds.call;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code call_records}. */
public interface CallRecordRepository extends JpaRepository<CallRecord, UUID> {

    /** Danh sách cuộc gọi của một người dùng, mới nhất trước, có phân trang. */
    Page<CallRecord> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);

    /** Tìm cuộc gọi theo id, chỉ khi nó thuộc về đúng người dùng đó. */
    Optional<CallRecord> findByIdAndUserId(UUID id, UUID userId);

    /** Cuộc gọi có lần phân tích nào đang chờ hoặc đang chạy không. */
    @Query(value = "select exists(select 1 from analyses a where a.call_record_id = :callId "
            + "and a.status in ('PENDING', 'PROCESSING'))", nativeQuery = true)
    boolean hasUnfinishedAnalysis(@Param("callId") UUID callId);
}
