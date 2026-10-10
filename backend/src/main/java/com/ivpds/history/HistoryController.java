package com.ivpds.history;

import com.ivpds.analysis.Analysis;
import com.ivpds.analysis.RiskResult;
import com.ivpds.common.PageResponse;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import com.ivpds.history.CallHistoryQueries.Filter;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * API lịch sử phân tích của người dùng đang đăng nhập: danh sách có lọc và chi tiết từng cuộc gọi.
 * Xóa một cuộc gọi khỏi lịch sử dùng {@code DELETE /api/v1/calls/{id}}.
 */
@RestController
@RequestMapping("/api/v1/history")
@Tag(name = "History")
public class HistoryController {

    static final int MAX_PAGE_SIZE = 100;

    private final CallHistoryQueries queries;

    public HistoryController(CallHistoryQueries queries) {
        this.queries = queries;
    }

    /**
     * Danh sách cuộc gọi kèm kết quả phân tích mới nhất, mới nhất trước.
     *
     * @param riskLevel    chỉ cuộc gọi có mức rủi ro này
     * @param status       chỉ cuộc gọi có lần phân tích mới nhất ở trạng thái này
     * @param from         từ thời điểm gửi lên này (ISO 8601)
     * @param to           trước thời điểm gửi lên này
     * @param callerNumber các chữ số có trong số người gọi
     */
    @GetMapping
    @Operation(summary = "List the signed-in user's calls with their latest analysis, newest first")
    public PageResponse<HistoryResponse> list(@AuthenticationPrincipal Jwt jwt,
            @RequestParam(required = false) RiskResult.Level riskLevel,
            @RequestParam(required = false) Analysis.Status status,
            @RequestParam(required = false) Instant from,
            @RequestParam(required = false) Instant to,
            @RequestParam(required = false) String callerNumber,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Filter filter = new Filter(userId(jwt), riskLevel, status, from, to, PhoneNumbers.searchDigits(callerNumber));
        PageResponse<CallHistoryQueries.Row> rows = queries.search(filter, Math.max(page, 0),
                Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        return new PageResponse<>(rows.items().stream().map(row -> HistoryResponse.from(row, false, false)).toList(),
                rows.page(), rows.size(), rows.totalItems(), rows.totalPages());
    }

    /** Chi tiết một cuộc gọi: kết quả phân tích mới nhất kèm transcript đầy đủ. */
    @GetMapping("/{callId}")
    @Operation(summary = "One call with the full result and transcript of its latest analysis")
    public HistoryResponse get(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID callId) {
        return queries.find(callId, userId(jwt))
                .map(row -> HistoryResponse.from(row, true, false))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CALL_NOT_FOUND", "Call not found."));
    }

    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
