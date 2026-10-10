package com.ivpds.blacklist;

import com.ivpds.blacklist.BlacklistReportService.AdminReportResponse;
import com.ivpds.blacklist.BlacklistReportService.ReportResponse;
import com.ivpds.common.PageResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API báo cáo số lừa đảo. Người dùng đã đăng nhập gửi và xem báo cáo của mình; các API dưới
 * {@code /api/v1/admin/blacklist/reports} chỉ dành cho ADMIN (quy tắc phân quyền nằm ở cấu hình bảo mật chung).
 */
@RestController
@Tag(name = "Blacklist reports")
public class BlacklistReportController {

    private final BlacklistReportService reportService;

    public BlacklistReportController(BlacklistReportService reportService) {
        this.reportService = reportService;
    }

    /** Báo cáo một số: gửi {@code phoneNumber}, hoặc {@code callId} của một cuộc gọi của mình, hoặc cả hai. */
    public record SubmitRequest(String phoneNumber, UUID callId, String reason) {
    }

    /** Lý do ghi vào danh sách đen khi duyệt; bỏ trống thì dùng lý do của báo cáo. */
    public record ApproveRequest(String reason) {
    }

    @PostMapping("/api/v1/blacklist/reports")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Report a phone number as a scam number; an administrator reviews it")
    public ReportResponse submit(@AuthenticationPrincipal Jwt jwt, @RequestBody SubmitRequest request) {
        return reportService.submit(userId(jwt), request.phoneNumber(), request.callId(), request.reason());
    }

    @GetMapping("/api/v1/blacklist/reports")
    @Operation(summary = "List the signed-in user's own reports, newest first")
    public PageResponse<ReportResponse> mine(@AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return reportService.mine(userId(jwt), page, size);
    }

    @GetMapping("/api/v1/admin/blacklist/reports")
    @Operation(summary = "Admin: list reported numbers, newest first")
    public PageResponse<AdminReportResponse> list(@RequestParam(required = false) BlacklistReport.Status status,
            @RequestParam(required = false) String query,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return reportService.search(status, query, page, size);
    }

    @PostMapping("/api/v1/admin/blacklist/reports/{id}/approve")
    @Operation(summary = "Admin: approve a report and blacklist its number")
    public AdminReportResponse approve(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id,
            @RequestBody(required = false) ApproveRequest request) {
        return reportService.approve(userId(jwt), id, request == null ? null : request.reason());
    }

    @PostMapping("/api/v1/admin/blacklist/reports/{id}/reject")
    @Operation(summary = "Admin: reject a report")
    public AdminReportResponse reject(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        return reportService.reject(userId(jwt), id);
    }

    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
