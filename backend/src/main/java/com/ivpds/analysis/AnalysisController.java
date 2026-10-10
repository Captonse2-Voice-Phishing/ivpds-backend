package com.ivpds.analysis;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API phân tích cuộc gọi. Mọi API đều cần đăng nhập và chỉ làm việc với cuộc gọi của chính người dùng.
 * Phân tích chạy ở nền: gửi yêu cầu rồi hỏi lại lần phân tích mới nhất cho tới khi nó COMPLETED hoặc FAILED.
 */
@RestController
@RequestMapping("/api/v1/calls/{callId}/analyses")
@Tag(name = "Analyses")
public class AnalysisController {

    private final AnalysisService analysisService;

    public AnalysisController(AnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    /** Yêu cầu phân tích (hoặc phân tích lại) một cuộc gọi; trả về ngay với trạng thái PENDING. */
    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    @Operation(summary = "Request an analysis of a call; it runs in the background")
    public AnalysisResponse start(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID callId) {
        return analysisService.start(userId(jwt), callId);
    }

    /** Trạng thái và kết quả của lần phân tích mới nhất. */
    @GetMapping("/latest")
    @Operation(summary = "Status and result of the most recent analysis of a call")
    public AnalysisResponse latest(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID callId) {
        return analysisService.latest(userId(jwt), callId);
    }

    /** Mọi lần phân tích của cuộc gọi, mới nhất trước. */
    @GetMapping
    @Operation(summary = "All analyses of a call, newest first")
    public List<AnalysisResponse> list(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID callId) {
        return analysisService.list(userId(jwt), callId);
    }

    /** Lấy id người dùng từ access token. */
    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
