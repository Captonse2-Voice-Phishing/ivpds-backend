package com.ivpds.blacklist;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Truy cập dữ liệu bảng {@code blacklist_numbers}. */
public interface BlacklistRepository extends JpaRepository<BlacklistNumber, UUID> {

    /** Tìm một số đã chuẩn hóa, dù đang chặn hay đã gỡ. */
    Optional<BlacklistNumber> findByPhoneNumber(String phoneNumber);

    /** Tìm một số đã chuẩn hóa, chỉ khi nó đang bị chặn. */
    Optional<BlacklistNumber> findByPhoneNumberAndActiveTrue(String phoneNumber);

    /** Trong các số đã cho, những số đang bị chặn. */
    List<BlacklistNumber> findByPhoneNumberInAndActiveTrue(Collection<String> phoneNumbers);

    /**
     * Danh sách cho trang quản trị, mới nhất trước.
     *
     * @param digits chuỗi chữ số cần có trong số điện thoại, hoặc rỗng để không lọc
     * @param active lọc theo trạng thái, hoặc null để lấy cả hai
     */
    @Query("""
            select b from BlacklistNumber b
             where (:digits = '' or b.phoneNumber like concat('%', :digits, '%'))
               and (:active is null or b.active = :active)
             order by b.createdAt desc
            """)
    Page<BlacklistNumber> search(@Param("digits") String digits, @Param("active") Boolean active, Pageable pageable);
}
