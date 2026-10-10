package com.ivpds.blacklist;

import com.ivpds.call.CallRecord;
import com.ivpds.call.CallRecordRepository;
import com.ivpds.common.PageResponse;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Nghiệp vụ báo cáo số lừa đảo: người dùng báo cáo một số (thường là số vừa gọi cho mình), quản trị viên duyệt
 * hoặc từ chối. Chỉ khi được duyệt, số mới vào danh sách đen.
 */
@Service
public class BlacklistReportService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_REASON_LENGTH = 1000;
    /** Số báo cáo đang chờ duyệt tối đa của một người dùng, để một tài khoản không làm ngập hàng chờ. */
    static final int MAX_PENDING_PER_USER = 20;

    private final BlacklistReportRepository reports;
    private final BlacklistRepository blacklist;
    private final CallRecordRepository calls;

    public BlacklistReportService(BlacklistReportRepository reports, BlacklistRepository blacklist,
            CallRecordRepository calls) {
        this.reports = reports;
        this.blacklist = blacklist;
        this.calls = calls;
    }

    /** Một báo cáo, như người báo cáo nhìn thấy. */
    public record ReportResponse(UUID id, String phoneNumber, UUID callId, String reason,
            BlacklistReport.Status status, Instant createdAt, Instant reviewedAt) {

        static ReportResponse from(BlacklistReport r) {
            return new ReportResponse(r.getId(), r.getPhoneNumber(), r.getCallId(), r.getReason(), r.getStatus(),
                    r.getCreatedAt(), r.getReviewedAt());
        }
    }

    /**
     * Một báo cáo, như quản trị viên nhìn thấy.
     *
     * @param reportsForNumber số người dùng khác nhau đã báo cáo số này (mọi trạng thái)
     * @param blacklisted      số này hiện có đang bị chặn không
     */
    public record AdminReportResponse(UUID id, String phoneNumber, UUID reporterId, UUID callId, String reason,
            BlacklistReport.Status status, UUID reviewedBy, Instant reviewedAt, Instant createdAt,
            long reportsForNumber, boolean blacklisted) {
    }

    // ----------------------------------------------------------- người dùng

    /**
     * Người dùng báo cáo một số. Phải có {@code rawPhoneNumber} hoặc {@code callId}; khi chỉ có {@code callId},
     * số bị báo cáo là số người gọi của cuộc gọi đó. Khi có cả hai và cuộc gọi có số người gọi, hai số phải trùng
     * nhau; cuộc gọi không có số người gọi thì nhận số người dùng nhập.
     */
    @Transactional
    public ReportResponse submit(UUID userId, String rawPhoneNumber, UUID callId, String reason) {
        String number = normalize(rawPhoneNumber);
        if (callId != null) {
            CallRecord call = calls.findByIdAndUserId(callId, userId).orElseThrow(() -> new ApiException(
                    HttpStatus.NOT_FOUND, "CALL_NOT_FOUND", "Call not found."));
            if (number == null) {
                number = call.getCallerNumber();
            } else if (call.getCallerNumber() != null && !number.equals(call.getCallerNumber())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "PHONE_NUMBER_MISMATCH",
                        "phoneNumber is not the caller number of this call.");
            }
        }
        if (number == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER", callId == null
                    ? "phoneNumber or callId is required."
                    : "This call has no caller number; send phoneNumber instead.");
        }
        String text = clean(reason);
        if (blacklist.findByPhoneNumberAndActiveTrue(number).isPresent()) {
            throw new ApiException(HttpStatus.CONFLICT, "PHONE_NUMBER_ALREADY_BLACKLISTED",
                    "This phone number is already in the blacklist.");
        }
        if (reports.existsByReporterIdAndPhoneNumber(userId, number)) {
            throw alreadyReported();
        }
        if (reports.countByReporterIdAndStatus(userId, BlacklistReport.Status.PENDING) >= MAX_PENDING_PER_USER) {
            throw new ApiException(HttpStatus.TOO_MANY_REQUESTS, "TOO_MANY_PENDING_REPORTS",
                    "You have too many reports waiting for review. Try again after they are reviewed.");
        }
        try {
            return ReportResponse.from(reports.saveAndFlush(new BlacklistReport(number, userId, callId, text)));
        } catch (DataIntegrityViolationException e) {
            // Cùng một người gửi hai báo cáo cho một số cùng lúc.
            throw alreadyReported();
        }
    }

    /** Các báo cáo của chính người dùng, mới nhất trước. */
    @Transactional(readOnly = true)
    public PageResponse<ReportResponse> mine(UUID userId, int page, int size) {
        return PageResponse.of(reports.findByReporterIdOrderByCreatedAtDesc(userId, pageable(page, size)),
                ReportResponse::from);
    }

    // ------------------------------------------------------------- quản trị

    /** Danh sách cho trang quản trị; {@code status} null để lấy mọi trạng thái. */
    @Transactional(readOnly = true)
    public PageResponse<AdminReportResponse> search(BlacklistReport.Status status, String query, int page, int size) {
        String digits = query == null ? "" : PhoneNumbers.searchDigits(query);
        Page<BlacklistReport> found = status == null
                ? reports.search(digits, pageable(page, size))
                : reports.search(status, digits, pageable(page, size));
        Set<String> numbers = found.stream().map(BlacklistReport::getPhoneNumber).collect(Collectors.toSet());
        Map<String, Long> reportCounts = reportCounts(numbers);
        Set<String> blocked = numbers.isEmpty() ? Set.of() : blacklist.findByPhoneNumberInAndActiveTrue(numbers)
                .stream().map(BlacklistNumber::getPhoneNumber).collect(Collectors.toSet());
        return PageResponse.of(found, report -> adminView(report,
                reportCounts.getOrDefault(report.getPhoneNumber(), 0L), blocked.contains(report.getPhoneNumber())));
    }

    /**
     * Duyệt một báo cáo: đưa số vào danh sách đen (hoặc bật lại nếu số đã từng bị gỡ) và đánh dấu đã duyệt mọi
     * báo cáo đang chờ về cùng số đó.
     *
     * @param reason lý do ghi vào danh sách đen (người tra cứu sẽ thấy); null thì dùng lý do của báo cáo
     */
    @Transactional
    public AdminReportResponse approve(UUID adminId, UUID reportId, String reason) {
        BlacklistReport report = pending(reportId);
        String number = report.getPhoneNumber();
        String text = clean(reason);
        BlacklistNumber entry = blacklist.findByPhoneNumber(number).orElse(null);
        if (entry == null) {
            try {
                blacklist.saveAndFlush(new BlacklistNumber(number, text == null ? report.getReason() : text, adminId));
            } catch (DataIntegrityViolationException e) {
                // Một quản trị viên khác vừa thêm số này.
                throw new ApiException(HttpStatus.CONFLICT, "REPORT_REVIEW_CONFLICT",
                        "The blacklist changed while this report was being approved. Try again.");
            }
        } else {
            entry.setActive(true);
            if (text != null) {
                entry.changeReason(text);
            }
        }
        Instant now = Instant.now();
        reports.findByPhoneNumberAndStatus(number, BlacklistReport.Status.PENDING)
                .forEach(waiting -> waiting.review(BlacklistReport.Status.APPROVED, adminId, now));
        reports.flush();
        return adminView(report, reportCounts(Set.of(number)).getOrDefault(number, 0L), true);
    }

    /** Từ chối một báo cáo. Các báo cáo khác về cùng số không bị ảnh hưởng. */
    @Transactional
    public AdminReportResponse reject(UUID adminId, UUID reportId) {
        BlacklistReport report = pending(reportId);
        report.review(BlacklistReport.Status.REJECTED, adminId, Instant.now());
        reports.flush();
        String number = report.getPhoneNumber();
        return adminView(report, reportCounts(Set.of(number)).getOrDefault(number, 0L),
                blacklist.findByPhoneNumberAndActiveTrue(number).isPresent());
    }

    // -------------------------------------------------------------- nội bộ

    private BlacklistReport pending(UUID reportId) {
        BlacklistReport report = reports.findById(reportId).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,
                "BLACKLIST_REPORT_NOT_FOUND", "Report not found."));
        if (report.getStatus() != BlacklistReport.Status.PENDING) {
            throw new ApiException(HttpStatus.CONFLICT, "REPORT_ALREADY_REVIEWED",
                    "This report has already been " + report.getStatus().name().toLowerCase() + ".");
        }
        return report;
    }

    private Map<String, Long> reportCounts(Set<String> numbers) {
        Map<String, Long> counts = new HashMap<>();
        if (!numbers.isEmpty()) {
            List<Object[]> rows = reports.countByNumber(numbers);
            rows.forEach(row -> counts.put((String) row[0], (Long) row[1]));
        }
        return counts;
    }

    private static AdminReportResponse adminView(BlacklistReport r, long reportsForNumber, boolean blacklisted) {
        return new AdminReportResponse(r.getId(), r.getPhoneNumber(), r.getReporterId(), r.getCallId(), r.getReason(),
                r.getStatus(), r.getReviewedBy(), r.getReviewedAt(), r.getCreatedAt(), reportsForNumber, blacklisted);
    }

    private static Pageable pageable(int page, int size) {
        return PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
    }

    private static ApiException alreadyReported() {
        return new ApiException(HttpStatus.CONFLICT, "NUMBER_ALREADY_REPORTED",
                "You have already reported this phone number.");
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
