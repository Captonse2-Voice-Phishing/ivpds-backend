package com.ivpds.analysis;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code analyses}. */
public interface AnalysisRepository extends JpaRepository<Analysis, UUID> {

    /** Các lần phân tích của một cuộc gọi, mới nhất trước. */
    List<Analysis> findByCallRecordIdOrderByCreatedAtDesc(UUID callRecordId);

    /** Lần phân tích mới nhất của một cuộc gọi. */
    Optional<Analysis> findFirstByCallRecordIdOrderByCreatedAtDesc(UUID callRecordId);

    /** Cuộc gọi có lần phân tích nào đang ở một trong các trạng thái này không. */
    boolean existsByCallRecordIdAndStatusIn(UUID callRecordId, Collection<Analysis.Status> statuses);

    /**
     * Đánh dấu thất bại mọi lần phân tích còn dang dở. Dùng khi khởi động: hàng đợi xử lý nằm trong bộ nhớ
     * nên những lần phân tích chưa xong trước khi backend dừng sẽ không bao giờ được chạy tiếp.
     *
     * @return số dòng đã cập nhật
     */
    @Modifying
    @Query("""
            update Analysis a
               set a.status = com.ivpds.analysis.Analysis.Status.FAILED,
                   a.errorCode = :code, a.errorMessage = :message, a.completedAt = :now, a.updatedAt = :now
             where a.status in (com.ivpds.analysis.Analysis.Status.PENDING,
                                com.ivpds.analysis.Analysis.Status.PROCESSING)
            """)
    int failUnfinished(@Param("code") String code, @Param("message") String message, @Param("now") Instant now);
}
