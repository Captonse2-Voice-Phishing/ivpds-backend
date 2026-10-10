package com.ivpds.blacklist;

import com.ivpds.call.CallCreatedEvent;
import com.ivpds.common.PageResponse;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import com.ivpds.notification.Notification;
import com.ivpds.notification.NotificationService;
import com.ivpds.user.User;
import com.ivpds.user.UserRepository;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Nghiệp vụ danh sách đen: người dùng tra cứu một số, quản trị viên thêm, sửa, gỡ số, và hệ thống cảnh báo khi
 * người dùng nhận cuộc gọi từ một số đang bị chặn.
 */
@Service
public class BlacklistService {

    private static final Logger log = LoggerFactory.getLogger(BlacklistService.class);
    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_REASON_LENGTH = 1000;

    private final BlacklistRepository blacklist;
    private final UserRepository users;
    private final NotificationService notifications;

    public BlacklistService(BlacklistRepository blacklist, UserRepository users, NotificationService notifications) {
        this.blacklist = blacklist;
        this.users = users;
        this.notifications = notifications;
    }

    /**
     * Kết quả tra cứu một số điện thoại.
     *
     * @param phoneNumber số đã chuẩn hóa (dạng dùng để so sánh)
     * @param blacklisted số này có đang bị chặn không
     * @param reason      lý do bị chặn; null nếu không bị chặn
     * @param since       thời điểm số được đưa vào danh sách; null nếu không bị chặn
     */
    public record Lookup(String phoneNumber, boolean blacklisted, String reason, Instant since) {
    }

    /** Tra cứu một số bất kỳ. Số đã gỡ khỏi danh sách được báo là không bị chặn. */
    @Transactional(readOnly = true)
    public Lookup lookup(String rawPhoneNumber) {
        String number = normalize(rawPhoneNumber);
        if (number == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER", "phoneNumber is required.");
        }
        return blacklist.findByPhoneNumberAndActiveTrue(number)
                .map(entry -> new Lookup(number, true, entry.getReason(), entry.getCreatedAt()))
                .orElseGet(() -> new Lookup(number, false, null, null));
    }

    /**
     * Khi người dùng có một cuộc gọi mới (gửi file hoặc mở cuộc gọi trực tiếp) từ số đang bị chặn, tạo thông báo
     * cảnh báo, trừ khi người dùng đã tắt cảnh báo blacklist trong hồ sơ. Lỗi ở đây chỉ được ghi log.
     */
    @EventListener
    public void onCallCreated(CallCreatedEvent event) {
        if (event.callerNumber() == null) {
            return;
        }
        try {
            blacklist.findByPhoneNumberAndActiveTrue(event.callerNumber()).ifPresent(entry -> {
                boolean wantsAlerts = users.findById(event.userId()).map(User::isBlacklistAlertEnabled).orElse(false);
                if (wantsAlerts) {
                    notifications.create(event.userId(), Notification.Type.BLACKLISTED_CALLER,
                            "Số gọi đến nằm trong danh sách đen",
                            "Số %s đã bị báo cáo là số lừa đảo.%s Hãy cẩn thận với mọi yêu cầu từ số này."
                                    .formatted(entry.getPhoneNumber(),
                                            entry.getReason() == null ? "" : " Lý do: " + entry.getReason() + "."),
                            null, event.callId());
                }
            });
        } catch (RuntimeException e) {
            log.error("Could not check the blacklist for call {}", event.callId(), e);
        }
    }

    // ------------------------------------------------------------- quản trị

    /** Danh sách cho trang quản trị; {@code query} lọc theo các chữ số có trong số điện thoại. */
    @Transactional(readOnly = true)
    public PageResponse<BlacklistResponse> search(String query, Boolean active, int page, int size) {
        String digits = query == null ? "" : PhoneNumbers.searchDigits(query);
        return PageResponse.of(blacklist.search(digits, active,
                PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE))), BlacklistResponse::from);
    }

    /** Thêm một số vào danh sách đen. Số đã có trong danh sách (kể cả đã gỡ) thì báo trùng. */
    @Transactional
    public BlacklistResponse add(UUID adminId, String rawPhoneNumber, String reason) {
        String number = normalize(rawPhoneNumber);
        if (number == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER", "phoneNumber is required.");
        }
        if (blacklist.findByPhoneNumber(number).isPresent()) {
            throw alreadyListed();
        }
        try {
            return BlacklistResponse.from(blacklist.saveAndFlush(new BlacklistNumber(number, clean(reason), adminId)));
        } catch (DataIntegrityViolationException e) {
            // Hai quản trị viên thêm cùng một số cùng lúc.
            throw alreadyListed();
        }
    }

    /** Sửa lý do hoặc bật, tắt việc chặn một số; trường nào null thì giữ nguyên. */
    @Transactional
    public BlacklistResponse update(UUID id, String reason, Boolean active) {
        BlacklistNumber entry = find(id);
        if (reason != null) {
            entry.changeReason(clean(reason));
        }
        if (active != null) {
            entry.setActive(active);
        }
        return BlacklistResponse.from(entry);
    }

    /** Xóa hẳn một số khỏi danh sách. */
    @Transactional
    public void delete(UUID id) {
        blacklist.delete(find(id));
    }

    private BlacklistNumber find(UUID id) {
        return blacklist.findById(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,
                "BLACKLIST_ENTRY_NOT_FOUND", "Blacklist entry not found."));
    }

    private static ApiException alreadyListed() {
        return new ApiException(HttpStatus.CONFLICT, "PHONE_NUMBER_ALREADY_BLACKLISTED",
                "This phone number is already in the blacklist.");
    }

    private static String normalize(String rawPhoneNumber) {
        try {
            return PhoneNumbers.normalize(rawPhoneNumber);
        } catch (IllegalArgumentException e) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER",
                    "phoneNumber must contain 6 to 15 digits, optionally starting with +.");
        }
    }

    /** Lý do rỗng được lưu là null; lý do quá dài bị từ chối. */
    private static String clean(String reason) {
        if (reason == null || reason.isBlank()) {
            return null;
        }
        if (reason.length() > MAX_REASON_LENGTH) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED",
                    "reason must be at most " + MAX_REASON_LENGTH + " characters.");
        }
        return reason.trim();
    }
}
