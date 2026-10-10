package com.ivpds.phishingpattern;

import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code phishing_patterns}. */
public interface PhishingPatternRepository extends JpaRepository<PhishingPattern, UUID> {

    /** Các mẫu đang bật, cũ nhất trước (thứ tự ổn định giữa các lần gọi). */
    List<PhishingPattern> findByActiveTrueOrderByCreatedAtAsc();

    /**
     * Danh sách cho trang quản trị, mới nhất trước.
     *
     * @param text          chuỗi (chữ thường) cần có trong tên hoặc nội dung mẫu, hoặc rỗng để không lọc
     * @param indicatorCode lọc theo mã dấu hiệu, hoặc rỗng để không lọc
     * @param active        lọc theo trạng thái, hoặc null để lấy cả hai
     */
    @Query("""
            select p from PhishingPattern p
             where (:text = '' or lower(p.name) like concat('%', :text, '%')
                    or lower(p.pattern) like concat('%', :text, '%'))
               and (:indicatorCode = '' or p.indicatorCode = :indicatorCode)
               and (:active is null or p.active = :active)
             order by p.createdAt desc
            """)
    Page<PhishingPattern> search(@Param("text") String text, @Param("indicatorCode") String indicatorCode,
            @Param("active") Boolean active, Pageable pageable);
}
