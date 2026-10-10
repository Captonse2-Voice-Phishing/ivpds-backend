package com.ivpds.blacklist;

import java.time.Instant;
import java.util.UUID;

/**
 * Một dòng của danh sách đen, trả về cho quản trị viên.
 *
 * @param active    số đang bị chặn hay đã tạm gỡ
 * @param createdBy quản trị viên đã thêm số này
 */
public record BlacklistResponse(UUID id, String phoneNumber, String reason, boolean active, UUID createdBy,
        Instant createdAt, Instant updatedAt) {

    static BlacklistResponse from(BlacklistNumber entry) {
        return new BlacklistResponse(entry.getId(), entry.getPhoneNumber(), entry.getReason(), entry.isActive(),
                entry.getCreatedBy(), entry.getCreatedAt(), entry.getUpdatedAt());
    }
}
