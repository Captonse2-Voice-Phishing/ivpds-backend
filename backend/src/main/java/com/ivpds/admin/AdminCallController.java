package com.ivpds.admin;

import com.ivpds.analysis.Analysis;
import com.ivpds.analysis.RiskResult;
import com.ivpds.common.PageResponse;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import com.ivpds.history.CallHistoryQueries;
import com.ivpds.history.CallHistoryQueries.Filter;
import com.ivpds.history.HistoryResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * API theo dõi các cuộc gọi đã phân tích của mọi người dùng, chỉ dành cho ADMIN. Dùng để xem các cuộc gọi rủi ro
 * cao ({@code riskLevel=HIGH}) và chi tiết kết quả phân tích. Quản trị viên xem được transcript nhưng không tải
 * được file ghi âm.
 */
@RestController
@RequestMapping("/api/v1/admin/calls")
@Tag(name = "Admin: calls")
public class AdminCallController {

    private static final int MAX_PAGE_SIZE = 100;

    private final CallHistoryQueries queries;

    public AdminCallController(CallHistoryQueries queries) {
        this.queries = queries;
    }

    /** Danh sách cuộc gọi của mọi người dùng kèm kết quả phân tích mới nhất, mới nhất trước. */
    @GetMapping
    @Operation(summary = "Admin: list analysed calls of all users; filter by riskLevel=HIGH to watch high-risk calls")
    public PageResponse<HistoryResponse> list(
            @RequestParam(required = false) RiskResult.Level riskLevel,
            @RequestParam(required = false) Analysis.Status status,
            @RequestParam(required = false) UUID userId,
            @RequestParam(required = false) Instant from,
            @RequestParam(required = false) Instant to,
            @RequestParam(required = false) String callerNumber,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Filter filter = new Filter(userId, riskLevel, status, from, to, PhoneNumbers.searchDigits(callerNumber));
        PageResponse<CallHistoryQueries.Row> rows = queries.search(filter, Math.max(page, 0),
                Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        return new PageResponse<>(rows.items().stream().map(row -> HistoryResponse.from(row, false, true)).toList(),
                rows.page(), rows.size(), rows.totalItems(), rows.totalPages());
    }

    /** Chi tiết một cuộc gọi bất kỳ: chủ cuộc gọi, kết quả phân tích mới nhất và transcript. */
    @GetMapping("/{callId}")
    @Operation(summary = "Admin: one call with its owner, latest analysis and transcript")
    public HistoryResponse get(@PathVariable UUID callId) {
        return queries.find(callId, null)
                .map(row -> HistoryResponse.from(row, true, true))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CALL_NOT_FOUND", "Call not found."));
    }
}
