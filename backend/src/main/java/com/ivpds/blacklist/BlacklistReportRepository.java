package com.ivpds.blacklist;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code blacklist_reports}. */
public interface BlacklistReportRepository extends JpaRepository<BlacklistReport, UUID> {

    /** Các báo cáo của một người dùng, mới nhất trước. */
    Page<BlacklistReport> findByReporterIdOrderByCreatedAtDesc(UUID reporterId, Pageable pageable);

    boolean existsByReporterIdAndPhoneNumber(UUID reporterId, String phoneNumber);

    long countByReporterIdAndStatus(UUID reporterId, BlacklistReport.Status status);

    /** Mọi báo cáo về một số đang ở một trạng thái. */
    List<BlacklistReport> findByPhoneNumberAndStatus(String phoneNumber, BlacklistReport.Status status);

    /**
     * Danh sách cho trang quản trị, mới nhất trước.
     *
     * @param digits chuỗi chữ số cần có trong số điện thoại, hoặc rỗng để không lọc
     */
    @Query("""
            select r from BlacklistReport r
             where (:digits = '' or r.phoneNumber like concat('%', :digits, '%'))
             order by r.createdAt desc
            """)
    Page<BlacklistReport> search(@Param("digits") String digits, Pageable pageable);

    /** Như {@link #search(String, Pageable)} nhưng chỉ lấy các báo cáo ở một trạng thái. */
    @Query("""
            select r from BlacklistReport r
             where r.status = :status
               and (:digits = '' or r.phoneNumber like concat('%', :digits, '%'))
             order by r.createdAt desc
            """)
    Page<BlacklistReport> search(@Param("status") BlacklistReport.Status status, @Param("digits") String digits,
            Pageable pageable);

    /** Số người đã báo cáo mỗi số trong {@code numbers}; mỗi dòng là {@code [số điện thoại, số báo cáo]}. */
    @Query("""
            select r.phoneNumber, count(r) from BlacklistReport r
             where r.phoneNumber in :numbers group by r.phoneNumber
            """)
    List<Object[]> countByNumber(@Param("numbers") Collection<String> numbers);
}
